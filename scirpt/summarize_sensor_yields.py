#!/usr/bin/env python3
"""Summarize per-wafer sensor counts by grade for IME and IHEP."""

import csv
from collections import Counter
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "2nd_batch_results"
INPUT_DIRS = {
    "IME": BASE_PATH / "sensor_yields_by_grade_IME",
    "IHEP": BASE_PATH / "sensor_yields_by_grade",
}
OUTPUT_PATH = BASE_PATH / "yield_summary"
GRADES = ["A", "B", "C"]

counts = Counter()  # (grade, test, wafer_name) -> sensor count
wafers = set()

for test, input_dir in INPUT_DIRS.items():
    for grade_file in ("A", "B", "C"):
        with (input_dir / f"{grade_file}.csv").open(newline="") as file:
            for row in csv.DictReader(file):
                grade = row["Final_Status"]
                counts[grade if grade in ("A", "C") else "B", test, row["wafer_name"]] += 1
                wafers.add(row["wafer_name"])


def wafer_order(wafer_name):
    batch, number = wafer_name.split("_")
    return batch, int(number)


OUTPUT_PATH.mkdir(exist_ok=True)
for grade in GRADES:
    ime_total = ihep_total = 0
    with (OUTPUT_PATH / f"{grade}.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["wafer", "IME", "IHEP"])
        for wafer in sorted(wafers, key=wafer_order):
            ime = counts[grade, "IME", wafer]
            ihep = counts[grade, "IHEP", wafer]
            writer.writerow([wafer, ime, ihep])
            ime_total += ime
            ihep_total += ihep
        writer.writerow(["Total", ime_total, ihep_total])
