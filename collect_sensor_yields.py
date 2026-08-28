#!/usr/bin/env python3
"""Collect sensor yields into A, B, and C tables."""

import csv
from pathlib import Path


MAIN_PATH = Path("/Users/liao./cernbox/public/HGTD_sensor")
RESULTS_PATH = MAIN_PATH / "HGTD-analysis/results"
WAFER_PARTS_PATH = MAIN_PATH / "2nd_batch_95/wafer_parts_template.csv"
OUTPUT_PATH = RESULTS_PATH / "sensor_yields_by_grade"


with WAFER_PARTS_PATH.open(newline="", encoding="utf-8-sig", errors="replace") as file:
    wafer_serials = {
        f"B{row['batch_number']}_{int(row['serial_number'][-2:])}": row["serial_number"]
        for row in csv.DictReader(file)
    }

tables = {"A": [], "B": [], "C": []}
fieldnames = None

for yield_file in sorted(RESULTS_PATH.glob("*/sensorYield.csv")):
    wafer_name = yield_file.parent.name
    with yield_file.open(newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames
        for row in reader:
            grade = row["Final_Status"]
            table = grade if grade in ("A", "C") else "B"
            tables[table].append(
                {"wafer_serial_number": wafer_serials[wafer_name], **row}
            )

OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

for grade, rows in tables.items():
    with (OUTPUT_PATH / f"{grade}.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, ["wafer_serial_number", *fieldnames])
        writer.writeheader()
        writer.writerows(rows)
