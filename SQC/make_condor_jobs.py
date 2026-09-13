#!/usr/bin/env python3
# -----------------2026.09.13--------------------
# Generate IHEP HTCondor (hep_sub) job files for the SQC batch:
# one job per sensor, all submitted in ONE hep_sub call (same cluster id).
# Reads the same config.yaml as run_all_sqc.py; all paths baked into the job
# files are ABSOLUTE (main_path + relative), so run this on the machine where
# the jobs will run.
#
# Usage:
#   python3 make_condor_jobs.py <config.yaml>

import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_all_sqc import discover, find_cqc, load_wafer_temps

CONDOR_DIR = Path(__file__).parent / "condor"


def build_plan(cfg):
    main_path = Path(cfg["main_path"])
    sqc_root = main_path / cfg["sqc_folder"]
    cqc_root = main_path / cfg["cqc_fallback_folder"]
    cqc_sample = main_path / cfg["cqc_folder"]
    temps = load_wafer_temps(main_path / cfg["temp_file"])
    tn = float(cfg.get("tn", 20.0))

    plan = []
    for label, batch, wafer, pos, needle_dir in discover(sqc_root):
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
        needle_abs = str(needle_dir) + "/1-%d.csv"
        plan.append((label, tp, ime_tpl, needle_abs))
    return plan, tn


JOB_SH = """#!/bin/bash
# One SQC sensor per job. $1 = ProcId (0-based), maps to sensors.list line N+1.
set -e
JOB_DIR="{job_dir}"
[ -f "$JOB_DIR/root_env.sh" ] && source "$JOB_DIR/root_env.sh"

line=$(sed -n "$(( $1 + 1 ))p" "$JOB_DIR/sensors.list")
if [ -z "$line" ]; then echo "empty sensors.list line for ProcId=$1"; exit 1; fi
IFS='|' read -r label tp ime_tpl needle_tpl <<< "$line"

out="$JOB_DIR/results/$label"
mkdir -p "$out"
root -b -q "{macro}($tp,{tn},\\"$ime_tpl\\",\\"$needle_tpl\\",\\"$out/\\")" \\
    > "$out/root.log" 2>&1
echo "done: $label -> $out"
"""

ROOT_ENV_SH = """#!/bin/bash
# Set up cluster ROOT here if it is not already in PATH on the worker nodes.
echo "WARNING: root_env.sh not configured, assuming root is in PATH" >&2
"""

SUBMIT_SH = """#!/bin/bash
# Submit all sensors in ONE hep_sub call: N sensors = N ProcIds (0..N-1)
# under the same cluster id. Run from the condor/ directory.
set -e
cd "$(dirname "$0")"
N=$(wc -l < sensors.list | tr -d ' ')
hep_sub job.sh -argu "%{ProcId}" -n "$N"
echo "submitted $N jobs under one cluster id; check with: hep_q -u $USER"
"""

COLLECT_PY = """#!/usr/bin/env python3
# After all jobs finish, run in condor/: python3 collect_results.py
import csv, glob, os
rows = []
for f in sorted(glob.glob("results/*/crosscheck.csv")):
    label = os.path.basename(os.path.dirname(f))
    with open(f) as fh:
        for r in csv.DictReader(fh):
            rows.append({"label": label, **r})
keys = ["label", "Group", "Mean", "RMS", "VbdMin", "RMS/Mean",
        "IRatio", "LKGMin", "LKGMax", "Valid"]
with open("summary_all.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
print(f"summary_all.csv: {len(rows)} rows from {len(glob.glob('results/*'))} sensors")
"""


def main():
    config_file = sys.argv[1]
    with open(config_file) as fh:
        cfg = yaml.safe_load(fh)
    main_path = Path(cfg["main_path"])
    macro = main_path / cfg["macro"]

    plan, tn = build_plan(cfg)
    print(f"Plan: {len(plan)} sensors -> {CONDOR_DIR}")
    CONDOR_DIR.mkdir(exist_ok=True)

    with open(CONDOR_DIR / "sensors.list", "w") as fh:
        for label, tp, ime_abs, needle_abs in plan:
            fh.write(f"{label}|{tp}|{ime_abs}|{needle_abs}\n")

    job_sh = JOB_SH.format(job_dir=CONDOR_DIR, macro=macro, tn=tn)
    (CONDOR_DIR / "job.sh").write_text(job_sh)
    (CONDOR_DIR / "root_env.sh").write_text(ROOT_ENV_SH)
    (CONDOR_DIR / "submit_all.sh").write_text(SUBMIT_SH)
    (CONDOR_DIR / "collect_results.py").write_text(COLLECT_PY)
    for name in ("job.sh", "submit_all.sh", "root_env.sh"):
        os.chmod(CONDOR_DIR / name, 0o755)
    print("Files:", sorted(p.name for p in CONDOR_DIR.iterdir()))


if __name__ == "__main__":
    main()
