#!/usr/bin/env python3
"""Write IHEP and IME rows for sensors with different final statuses.

Usage:
    compare_sensor_yields.py IHEP_DIR --ime IME_DIR [--sample SAMPLE_DIR]

IHEP_DIR holds the per-wafer analysis results (*/sensorYield*.csv); IME_DIR
holds the vendor per-wafer yields (typically the CQC_sample batch tree).
sensor_yield_differences.csv is written into IHEP_DIR. The wafer -> serial
mapping is read from the 20WS* subdirectories shipped with each wafer; pass
--sample when IME_DIR does not contain them.
"""

import argparse
import csv
from pathlib import Path


MAIN_PATH = Path("/eos/user/l/liaoc/public/HGTD_sensor")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("ihep_dir", help="directory holding the per-wafer IHEP results")
parser.add_argument(
    "--ime", required=True, help="directory holding the per-wafer IME yields"
)
parser.add_argument(
    "--sample",
    help="sample tree for the wafer -> serial mapping (default: IME_DIR itself)",
)
args = parser.parse_args()

IHEP_PATH = MAIN_PATH / args.ihep_dir
IME_PATH = MAIN_PATH / args.ime
SAMPLE_PATH = MAIN_PATH / args.sample if args.sample else IME_PATH
OUTPUT_PATH = IHEP_PATH / "sensor_yield_differences.csv"


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

ime_yields = {}
for wafer_path in IME_PATH.iterdir():
    if not wafer_path.is_dir() or not wafer_path.name.startswith("B"):
        continue
    ime_yields[wafer_path.name.replace("-", "_")] = find_yield_file(wafer_path)

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

for ihep_file in sorted(IHEP_PATH.glob("*/sensorYield*.csv")):
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
