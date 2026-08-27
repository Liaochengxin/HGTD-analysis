#!/usr/bin/env python3
"""Run Card52_v3.C with paths supplied by a yaml config file."""

import csv
import subprocess
import sys
from pathlib import Path

import yaml


config_file = Path(sys.argv[1])
with config_file.open() as file:
    config = yaml.safe_load(file)

main_path = Path(config["main_path"])
zip_path = main_path / config["zip_path"]
unzip_path = main_path / config["unzip_path"]
input_prefix = main_path / config["input_prefix"]
temperature_file = main_path / config["temp_file"]
root_macro = main_path / config["root_macro"]
result_path = main_path / config["output_path"] / config["wafer_name"]

serial_number = zip_path.stem
with temperature_file.open(encoding="utf-8-sig", errors="replace", newline="") as file:
    temperatures = {row[0]: float(row[1]) for row in list(csv.reader(file))[1:] if row}
temperature = temperatures[serial_number]

unzip_path.mkdir(parents=True, exist_ok=True)
subprocess.run(["unzip", "-q", "-j", "-o", zip_path, "-d", unzip_path])

result_path.mkdir(parents=True, exist_ok=True)
root_call = f'{root_macro}("{input_prefix}",{temperature})'
with (result_path / "run.log").open("w") as log:
    subprocess.run(
        ["root", "-l", "-b", "-q", root_call],
        cwd=result_path,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

sensor_files = [
    "VMap_Sensor_{}.png",
    "BVHist_Sensor_{}.png",
    "Leakage_Current_Sensor_{}.png",
    "Leakage_Current_Full_Sensor_{}.png",
    "IDist_Sensor_{}.png",
]

for sensor in range(1, 53):
    sensor_path = result_path / f"sensor_{sensor}"
    sensor_path.mkdir(exist_ok=True)
    for filename in sensor_files:
        source = result_path / filename.format(sensor)
        source.replace(sensor_path / source.name)

print(f"Finished {serial_number} at {temperature}°C")
print(f"Results: {result_path}")
