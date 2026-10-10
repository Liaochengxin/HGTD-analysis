#!/usr/bin/env python3
"""Collect sensor yields into A, B, and C tables.

Usage:
    collect_sensor_yields.py INPUT_DIR [--sample SAMPLE_DIR] [--label LABEL]
                           [--output OUTPUT_DIR]

INPUT_DIR holds one directory per wafer (Bxx_N) with a sensorYields.csv.
The wafer -> serial mapping is read from the 20WS* data subdirectory shipped
with each wafer; pass --sample pointing at the matching CQC_sample batch tree
when INPUT_DIR is an analysis-results directory without them. --label suffixes
the output folder name (e.g. IME -> sensor_yields_by_grade_IME); the folder is
written into INPUT_DIR unless --output gives another parent (e.g. the results
folder, so a run on the sample tree does not pollute CQC_sample).
"""

import argparse
import csv
from pathlib import Path


MAIN_PATH = Path("/eos/user/l/liaoc/public/HGTD_sensor")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("input_dir", help="directory holding the per-wafer results")
# if input_dir is results fold, please add sample option to point to the matching CQC_sample batch tree for the wafer -> serial mapping
parser.add_argument(
    "--sample",
    help="matching CQC_sample batch tree for the wafer -> serial mapping "
    "(default: INPUT_DIR itself)",
)
parser.add_argument(
    "--label", help="suffix for the output folder, e.g. IME (default: none)"
)
parser.add_argument(
    "--output",
    help="parent directory for the sensor_yields_by_grade* output folder "
    "(default: INPUT_DIR itself)",
)
args = parser.parse_args()

INPUT_PATH = MAIN_PATH / args.input_dir
SAMPLE_PATH = MAIN_PATH / args.sample if args.sample else INPUT_PATH
OUTPUT_PARENT = MAIN_PATH / args.output if args.output else INPUT_PATH
OUTPUT_PATH = OUTPUT_PARENT / f"sensor_yields_by_grade{'_' + args.label if args.label else ''}"


def find_yield_file(wafer_path):
    """Yield summary naming evolved: sensorYields.csv (current unified name),
    sensorYield.csv (older runs), <serial>.csv (oldest)."""
    for name in ("sensorYields.csv", "sensorYield.csv"):
        f = wafer_path / name
        if f.exists():
            return f
    return next(wafer_path.glob("20WS*.csv"))


def wafer_serial(sample_path):
    """Serial number = the 20WS* data subfolder shipped with the wafer."""
    return next(
        path.name
        for path in sorted(sample_path.iterdir())
        if path.is_dir() and path.name.startswith("20WS")
    )


wafer_serials = {
    path.name: wafer_serial(path)
    for path in sorted(SAMPLE_PATH.iterdir())
    if path.is_dir() and path.name.startswith("B")
}

tables = {"A": [], "B": [], "C": []}
fieldnames = None

for wafer_path in sorted(
    path for path in INPUT_PATH.iterdir() if path.is_dir() and path.name.startswith("B")
):
    yield_file = find_yield_file(wafer_path)

    wafer_name = wafer_path.name.replace("-", "_")
    with yield_file.open(newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames
        for row in reader:
            grade = row["Final_Status"]
            table = grade if grade in ("A", "C") else "B"
            tables[table].append(
                {
                    "wafer_serial_number": wafer_serials[wafer_name],
                    "wafer_name": wafer_name,
                    **row,
                }
            )

OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

for grade, rows in tables.items():
    with (OUTPUT_PATH / f"{grade}.csv").open("w", newline="") as file:
        writer = csv.DictWriter(
            file, ["wafer_serial_number", "wafer_name", *fieldnames]
        )
        writer.writeheader()
        writer.writerows(rows)
