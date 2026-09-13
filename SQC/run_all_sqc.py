#!/usr/bin/env python3
# -----------------2026.09.13--------------------
# Batch runner for temp_vbdmin_cross_toIME_v2.C, driven by a yaml config.
# Scans <sqc_folder>/B*/W*_P*/SweepVoltage0, matches each sensor against the
# CQC data, runs the ROOT macro once per sensor, aggregates crosscheck.csv.
#
# Usage:
#   python3 run_all_sqc.py <config.yaml>                # run everything
#   python3 run_all_sqc.py <config.yaml> --filter B31   # label substring filter
#   python3 run_all_sqc.py <config.yaml> --dry-run      # plan only

import argparse
import csv
import re
import subprocess
import time
from pathlib import Path

import yaml


def load_wafer_temps(path):
    """Serial rule: 20WS0013 + batch last digit + {wafer:05d}."""
    temps = {}
    if not path.exists():
        return temps
    with open(path, errors="ignore") as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or not row[0].strip().startswith("20WS"):
                continue
            m = re.search(r"(\d)(\d{5})$", row[0].strip())
            if not m:
                continue
            try:
                temps[(int(m.group(1)), int(m.group(2)))] = float(row[1].strip())
            except ValueError:
                continue
    return temps


def find_cqc(cqc_root, cqc_sample, batch, wafer, pos, temps=None):
    """CQC match: CQC_sample real match > test_CQC exact serial > placeholder."""
    sensor_serial = f"20WS2{batch:03d}{wafer:04d}{pos:02d}"
    wafer_dir = cqc_sample / f"B{batch}_{wafer}"
    if wafer_dir.is_dir():
        data_dirs = [
            d for d in wafer_dir.iterdir()
            if d.is_dir() and d.name.startswith("20WS")
        ]
        if data_dirs:
            wafer_serial = data_dirs[0].name
            if (data_dirs[0] / f"{sensor_serial}-1.csv").exists():
                tp = temps.get(wafer_serial) if temps is not None else None
                prefix = str(data_dirs[0] / sensor_serial) + "-%d.csv"
                return prefix, tp, f"matched:{wafer_dir.name}"
    if cqc_root.exists():
        for d in sorted(cqc_root.iterdir()):
            if d.is_dir() and (d / f"{sensor_serial}-1.csv").exists():
                return str(d / sensor_serial) + "-%d.csv", None, "matched"
        for d in sorted(cqc_root.iterdir()):
            if d.is_dir():
                files = sorted(d.glob("*-1.csv"))
                if files:
                    prefix = files[0].name[: -len("-1.csv")]
                    return str(d / prefix) + "-%d.csv", None, "placeholder"
    if cqc_sample.exists():
        for d in sorted(cqc_sample.glob("B*/20WS*")):
            files = sorted(d.glob("*-1.csv"))
            if files:
                prefix = files[0].name[: -len("-1.csv")]
                return str(d / prefix) + "-%d.csv", None, "placeholder"
    return None, None, "missing"


def discover(sqc_root):
    """Return [(label, batch, wafer, pos, needle_dir)], label like 1st-B31-W22-P3."""
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
    with open(log, "w") as lh:
        proc = subprocess.run(["root", "-b", "-q", macro_args],
                              capture_output=True, text=True)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--filter", default="", help="substring filter on label")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    main_path = Path(cfg["main_path"])
    sqc_root = main_path / cfg["sqc_folder"]
    cqc_root = main_path / cfg["cqc_fallback_folder"]
    cqc_sample = main_path / cfg["cqc_folder"]
    temps = load_wafer_temps(main_path / cfg["temp_file"])
    macro = main_path / cfg["macro"]
    out_root = main_path / cfg["output_path"]
    tn = float(cfg.get("tn", 20.0))

    sensors = discover(sqc_root)
    if args.filter:
        sensors = [s for s in sensors if args.filter in s[0]]
    print(f"Found {len(sensors)} sensors under {sqc_root}")
    if not sensors:
        raise SystemExit(1)

    plan = []
    for label, batch, wafer, pos, needle_dir in sensors:
        ime_tpl, tp, src = find_cqc(cqc_root, cqc_sample, batch, wafer, pos, temps)
        if ime_tpl is None:
            print(f"  [skip] {label}: no CQC data at all")
            continue
        if tp is None:
            tp = temps.get((batch % 10, wafer), 20.0)
        n_files = len(list(needle_dir.glob("1-*.csv")))
        if n_files == 0:
            print(f"  [skip] {label}: needle dir is empty")
            continue
        if n_files != 225:
            print(f"  [warn] {label}: needle has {n_files}/225 files")
        outdir = out_root / label
        macro_args = f'{macro}({tp},{tn},"{ime_tpl}","{needle_dir}/1-%d.csv","{outdir}/")'
        plan.append((label, macro_args, outdir, tp, src))
        print(f"  {label}: Tp={tp} ({src}), out={outdir}")

    if args.dry_run:
        print("\nDry run, nothing executed.")
        return

    summary_rows = []
    t0 = time.time()
    for i, (label, macro_args, outdir, tp, src) in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] {label} (elapsed {time.time()-t0:.0f}s) ...",
              flush=True)
        if not run_one(macro_args, outdir, outdir / "run.log"):
            print(f"  FAILED - see {outdir/'run.log'}")
            continue
        cc = read_crosscheck(outdir)
        for group, r in cc.items():
            summary_rows.append({"label": label, "Tp": tp, "cqc": src, **r})
        needle = cc.get("Needle", {})
        print(f"  Needle: Mean={needle.get('Mean')} RMS={needle.get('RMS')} "
              f"VbdMin={needle.get('VbdMin')} IRatio={needle.get('IRatio')} "
              f"Valid={needle.get('Valid')}")

    if summary_rows:
        summary = out_root / "summary_all.csv"
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
