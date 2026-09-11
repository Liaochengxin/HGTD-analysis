#!/usr/bin/env python3
"""Write IHEP and IME rows for sensors with different final statuses."""

import csv
from pathlib import Path


MAIN_PATH = Path("/Users/liao./cernbox/public/HGTD_sensor")
IME_PATH = MAIN_PATH / "2nd_batch_95"
IHEP_PATH = MAIN_PATH / "HGTD-analysis/results"
WAFER_PARTS_PATH = IME_PATH / "wafer_parts_template.csv"
OUTPUT_PATH = IHEP_PATH / "sensor_yield_differences.csv"


with WAFER_PARTS_PATH.open(newline="", encoding="utf-8-sig", errors="replace") as file:
    wafer_serials = {
        f"B{row['batch_number']}_{int(row['serial_number'][-2:])}": row["serial_number"]
        for row in csv.DictReader(file)
    }

ime_yields = {}
for wafer_path in IME_PATH.iterdir():
    if not wafer_path.is_dir() or not wafer_path.name.startswith("B"):
        continue
    yield_file = wafer_path / "sensorYield.csv"
    if not yield_file.exists():
        yield_file = next(wafer_path.glob("20WS*.csv"))
    ime_yields[wafer_path.name.replace("-", "_")] = yield_file

fieldnames = [
    "Test",
    "wafer_serial_number",
    "wafer_name",
    "Sensor",
    "Vbd_Average",
    "Vbd_Min",
    "Vbd_Rms",
    "Vbd_Rms_ov_Vbd",
    "Vbd_Status",
    "I_Average",
    "I_Max",
    "I_Min",
    "I_Ratio",
    "Final_Status",
]
rows = []

for ihep_file in sorted(IHEP_PATH.glob("*/sensorYield.csv")):
    wafer_name = ihep_file.parent.name
    if wafer_name not in ime_yields:
        continue

    with ihep_file.open(newline="") as file:
        ihep_rows = {row["Sensor"]: row for row in csv.DictReader(file)}
    with ime_yields[wafer_name].open(newline="") as file:
        ime_rows = {row["Sensor"]: row for row in csv.DictReader(file)}

    for sensor in sorted(ihep_rows, key=int):
        ihep_row = ihep_rows[sensor]
        ime_row = ime_rows[sensor]
        if ihep_row["Final_Status"] == ime_row["Final_Status"]:
            continue

        prefix = {
            "wafer_serial_number": wafer_serials[wafer_name],
            "wafer_name": wafer_name,
        }
        rows.append({"Test": "IHEP", **prefix, **ihep_row})
        rows.append({"Test": "IME", **prefix, **ime_row})

with OUTPUT_PATH.open("w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
