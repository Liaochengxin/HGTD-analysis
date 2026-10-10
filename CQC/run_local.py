#!/usr/bin/env python3
"""Run Card52_v3.C with paths supplied by a yaml config file.

The wafer CSVs are expected to be already extracted by script/unzip_cqc.py;
this script only reads them (config key input_prefix) and runs the macro.
"""

import csv
import subprocess
import sys
from pathlib import Path

import yaml


config_file = Path(sys.argv[1])
with config_file.open() as file:
    config = yaml.safe_load(file)

main_path = Path(config["main_path"])
input_prefix = main_path / config["input_prefix"]
temperature_file = main_path / config["temp_file"]
root_macro = main_path / config["root_macro"]
result_path = main_path / config["output_path"] / config["wafer_name"].replace("-", "_")

serial_number = config["serial_number"]
print(
    f"[CQC] Preparing wafer={config['wafer_name']} serial={serial_number} "
    f"input={input_prefix}",
    flush=True,
)
with temperature_file.open(encoding="utf-8-sig", errors="replace", newline="") as file:
    temperatures = {row[0]: float(row[1]) for row in list(csv.reader(file))[1:] if row}
temperature = temperatures[serial_number]

result_path.mkdir(parents=True, exist_ok=True)
root_call = f'{root_macro}("{input_prefix}",{temperature})'
run_log = result_path / "run.log"
print(
    f"[CQC] Starting ROOT at {temperature}°C; log={run_log}",
    flush=True,
)
with run_log.open("w") as log:
    subprocess.run(
        ["root", "-l", "-b", "-q", root_call],
        cwd=result_path,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
print("[CQC] ROOT completed; organizing sensor plots", flush=True)

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

print(f"[CQC] Finished {serial_number} at {temperature}°C", flush=True)
print(f"[CQC] Results: {result_path}", flush=True)
