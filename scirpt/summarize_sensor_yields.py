#!/usr/bin/env python3
"""Summarize per-wafer sensor counts by grade for IME and IHEP.

Usage:
    summarize_sensor_yields.py BASE_DIR

BASE_DIR holds the collect_sensor_yields.py outputs: sensor_yields_by_grade/
(required) and sensor_yields_by_grade_IME/ (optional). yield_summary/ is
written into BASE_DIR; without an IME side the tables carry the IHEP column
only. Paths are taken as given (absolute or CWD-relative), or relative to
the repository root.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path


MAIN_PATH = Path("/eos/user/l/liaoc/public/HGTD_sensor")
GRADES = ["A", "B", "C"]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("base_dir", help="parent of the sensor_yields_by_grade* folders")
args = parser.parse_args()

BASE_PATH = Path(args.base_dir)
if not BASE_PATH.exists():
    BASE_PATH = MAIN_PATH / args.base_dir
INPUT_DIRS = {
    "IME": BASE_PATH / "sensor_yields_by_grade_IME",
    "IHEP": BASE_PATH / "sensor_yields_by_grade",
}
TESTS = [test for test in INPUT_DIRS if INPUT_DIRS[test].is_dir()]
if not TESTS:
    raise SystemExit(f"no sensor_yields_by_grade*/ under {BASE_PATH}")
OUTPUT_PATH = BASE_PATH / "yield_summary"

counts = Counter()  # (grade, test, wafer_name) -> sensor count
wafers = set()

for test in TESTS:
    for grade_file in ("A", "B", "C"):
        with (INPUT_DIRS[test] / f"{grade_file}.csv").open(newline="") as file:
            for row in csv.DictReader(file):
                grade = row["Final_Status"]
                counts[grade if grade in ("A", "C") else "B", test, row["wafer_name"]] += 1
                wafers.add(row["wafer_name"])


def wafer_order(wafer_name):
    batch, number = wafer_name.split("_")
    return batch, int(number)


OUTPUT_PATH.mkdir(exist_ok=True)
for grade in GRADES:
    totals = {test: 0 for test in TESTS}
    with (OUTPUT_PATH / f"{grade}.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["wafer", *TESTS])
        for wafer in sorted(wafers, key=wafer_order):
            writer.writerow([wafer] + [counts[grade, t, wafer] for t in TESTS])
            for test in TESTS:
                totals[test] += counts[grade, test, wafer]
        writer.writerow(["Total", *[totals[test] for test in TESTS]])
