#!/usr/bin/env python3
"""Collect sensor yields into A, B, and C tables."""

import csv
import sys
from pathlib import Path


MAIN_PATH = Path("/Users/liao./cernbox/public/HGTD_sensor")
WAFER_PARTS_PATH = MAIN_PATH / "2nd_batch_95/wafer_parts_template.csv"
INPUT_PATH = MAIN_PATH / sys.argv[1]
OUTPUT_PATH = MAIN_PATH / "HGTD-analysis/results" / (
    "sensor_yields_by_grade_IME"
    if INPUT_PATH.name == "2nd_batch_95"
    else "sensor_yields_by_grade"
)


with WAFER_PARTS_PATH.open(newline="", encoding="utf-8-sig", errors="replace") as file:
    wafer_serials = {
        f"B{row['batch_number']}_{int(row['serial_number'][-2:])}": row["serial_number"]
        for row in csv.DictReader(file)
    }

tables = {"A": [], "B": [], "C": []}
fieldnames = None

for wafer_path in sorted(
    path for path in INPUT_PATH.iterdir() if path.is_dir() and path.name.startswith("B")
):
    yield_file = wafer_path / "sensorYield.csv"
    if not yield_file.exists():
        yield_file = next(wafer_path.glob("20WS*.csv"))

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
