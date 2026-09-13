#!/usr/bin/env python3
# -----------------2026.09.13--------------------
# Batch wrapper for temp_vbdmin_cross_toIME_v2.C
# Scans SQC_sample/<gen>/B<batch>/W<wafer>_P<pos>/SweepVoltage0, runs the ROOT
# macro once per sensor, and aggregates all crosscheck.csv into one summary.
#
# Usage:
#   python3 run_all_sqc.py                 # run everything found in SQC_sample
#   python3 run_all_sqc.py --filter B31    # only sensors whose label contains B31
#   python3 run_all_sqc.py --dry-run       # list what would run, execute nothing

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

MACRO = Path(__file__).parent / "temp_vbdmin_cross_toIME_v2.C"
BASE = Path(__file__).parents[2]  # HGTD_sensor/
DEFAULT_SQC = BASE / "SQC_sample"
DEFAULT_CQC = BASE / "test_CQC"
DEFAULT_TEMP = DEFAULT_CQC / "wafer_temperature_template.csv"
DEFAULT_OUT = BASE / "test_out"
TN_SQC = 20.0  # SQC (needle) temperature, fixed


def parse_args():
    p = argparse.ArgumentParser(description="Batch-run temp_vbdmin_cross_toIME_v2.C")
    p.add_argument("--sqc", type=Path, default=DEFAULT_SQC)
    p.add_argument("--cqc", type=Path, default=DEFAULT_CQC)
    p.add_argument("--temp-csv", type=Path, default=DEFAULT_TEMP)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--filter", default="", help="substring filter on sensor label")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def load_wafer_temps(path):
    """温度表序列号规则: 20WS0013 + 批次末位 + {wafer:05d}, 如 20WS0013100015 -> (31, 15) -> 21.8"""
    temps = {}
    if not path.exists():
        return temps
    with open(path, errors="ignore") as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or not row[0].strip().startswith("20WS"):
                continue
            sn = row[0].strip()
            m = re.search(r"(\d)(\d{5})$", sn)
            if not m:
                continue
            try:
                temps[(int(m.group(1)), int(m.group(2)))] = float(row[1].strip())
            except ValueError:
                continue
    return temps


def find_cqc(cqc_root, batch, wafer, pos):
    """返回 (探卡路径前缀含-%d, Tp, 来源标记)。先按序列号精确匹配, 否则用占位数据。"""
    serial = f"20WS2{batch:03d}{wafer:04d}{pos:02d}"
    if cqc_root.exists():
        for d in sorted(cqc_root.iterdir()):
            if d.is_dir() and (d / f"{serial}-1.csv").exists():
                return str(d / serial) + "-%d.csv", None, "matched"
        for d in sorted(cqc_root.iterdir()):  # placeholder: first available CQC set
            if d.is_dir():
                files = sorted(d.glob("*-1.csv"))
                if files:
                    prefix = files[0].name[: -len("-1.csv")]
                    return str(d / prefix) + "-%d.csv", None, "placeholder"
    return None, None, "missing"


def discover(sqc_root):
    """返回 [(label, needle_dir)], label 形如 1st-B31-W22-P3"""
    sensors = []
    for sv in sorted(sqc_root.glob("*/B*/W*_P*/SweepVoltage0")):
        m = re.match(r"W(\d+)_P(\d+)$", sv.parent.name)
        if not m:
            continue
        wafer, pos = int(m.group(1)), int(m.group(2))
        batch = int(sv.parent.parent.name.lstrip("B"))
        gen = "1st" if "1st" in sv.parents[1].parent.name else "2nd"
        label = f"{gen}-B{batch:02d}-W{wafer:02d}-P{pos}"
        sensors.append((label, batch, wafer, pos, sv))
    return sensors


def run_one(macro_args, outdir, log):
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = ["root", "-b", "-q", macro_args]
    with open(log, "w") as lh:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        lh.write(proc.stdout)
        lh.write(proc.stderr)
    return proc.returncode == 0


def read_crosscheck(outdir):
    f = outdir / "crosscheck.csv"
    if not f.exists():
        return {}
    with open(f) as fh:
        rows = list(csv.DictReader(fh))
    return {r["Group"]: r for r in rows}


def main():
    args = parse_args()
    temps = load_wafer_temps(args.temp_csv)
    sensors = discover(args.sqc)
    if args.filter:
        sensors = [s for s in sensors if args.filter in s[0]]
    print(f"Found {len(sensors)} sensors under {args.sqc}")
    if not sensors:
        sys.exit(1)

    # 第一遍: 解析配对与温度, 展示计划
    plan = []
    for label, batch, wafer, pos, needle_dir in sensors:
        ime_tpl, tp, src = find_cqc(args.cqc, batch, wafer, pos)
        if ime_tpl is None:
            print(f"  [skip] {label}: no CQC data available at all")
            continue
        if tp is None:
            tp = temps.get((batch % 10, wafer))
        if tp is None:
            tp = 20.0
        n_files = len(list(needle_dir.glob("1-*.csv")))
        if n_files == 0:
            print(f"  [skip] {label}: needle dir is empty")
            continue
        if n_files != 225:
            print(f"  [warn] {label}: needle has {n_files}/225 files")
        outdir = args.out / label
        macro_args = (
            f"{MACRO}({tp},{TN_SQC},"
            f'"{ime_tpl}","{needle_dir}/1-%d.csv","{outdir}/")'
        )
        plan.append((label, macro_args, outdir, tp, src))
        print(f"  {label}: Tp={tp} ({src}), out={outdir}")

    if args.dry_run:
        print("\nDry run, nothing executed.")
        return

    # 第二遍: 逐片执行 + 汇总
    summary_rows = []
    t0 = time.time()
    for i, (label, macro_args, outdir, tp, src) in enumerate(plan, 1):
        dt = time.time() - t0
        print(f"\n[{i}/{len(plan)}] {label} (elapsed {dt:.0f}s) ...", flush=True)
        ok = run_one(macro_args, outdir, outdir / "run.log")
        if not ok:
            print(f"  FAILED - see {outdir/'run.log'}")
            continue
        cc = read_crosscheck(outdir)
        for group, r in cc.items():
            summary_rows.append({"label": label, "Tp": tp, "cqc": src, **r})
        needle = cc.get("Needle", {})
        print(f"  Needle: Mean={needle.get('Mean')} RMS={needle.get('RMS')} "
              f"VbdMin={needle.get('VbdMin')} IRatio={needle.get('IRatio')} "
              f"Valid={needle.get('Valid')}")

    summary = args.out / "summary_all.csv"
    if summary_rows:
        keys = ["label", "Tp", "cqc", "Group", "Mean", "RMS", "VbdMin",
                "RMS/Mean", "IRatio", "LKGMin", "LKGMax", "Valid"]
        with open(summary, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(summary_rows)
    print(f"\nDone: {len(plan)} sensors in {time.time()-t0:.0f}s")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
