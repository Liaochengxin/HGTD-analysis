"""Validated per-wafer CQC yield tables shared by post-processing scripts."""

import csv
import re
from pathlib import Path

MAIN_PATH = Path("/eos/user/l/liaoc/public/HGTD_sensor")


def resolve_path(path):
    """Absolute paths stay explicit; relative paths are rooted on CERN EOS."""
    return MAIN_PATH / Path(path).expanduser()

WAFER_RE = re.compile(r"B(?P<batch>\d+)[_-](?P<wafer>\d+)")
GRADES = {"A": "A", "B": "B", "B1": "B", "B2": "B", "C": "C"}


def wafer_key(name):
    match = WAFER_RE.fullmatch(name)
    if match is None:
        raise ValueError(f"expected B<batch>_<wafer> or B<batch>-<wafer>: {name}")
    return int(match['batch']), int(match['wafer'])


def wafer_name(name):
    batch, wafer = wafer_key(name)
    return f"B{batch}_{wafer}"


def discover_wafers(root):
    if not root.is_dir():
        raise ValueError(f"batch directory does not exist: {root}")
    wafers = {}
    for path in sorted(root.iterdir()):
        if path.is_dir() and WAFER_RE.fullmatch(path.name):
            name = wafer_name(path.name)
            if name in wafers:
                raise ValueError(f"duplicate wafer identity {name}: {wafers[name]}, {path}")
            wafers[name] = path
    if not wafers:
        raise ValueError(f"no per-wafer B<batch>_<wafer> directories in {root}; select one batch")
    return dict(sorted(wafers.items(), key=lambda item: wafer_key(item[0])))


def find_yield_file(wafer_path):
    # Explicit supported schema versions; unrelated IV CSVs are never selected.
    candidates = [p for p in wafer_path.glob('*.csv')
                  if p.name in ('sensorYield.csv', 'sensorYields.csv')
                  or re.fullmatch(r'20WS\d+\.csv', p.name)]
    if len(candidates) != 1:
        raise ValueError(f"{wafer_path}: expected one sensor yield table, found {len(candidates)}")
    return candidates[0]


def wafer_serial(sample_path):
    candidates = sorted(p.name for p in sample_path.iterdir()
                        if p.is_dir() and re.fullmatch(r'20WS\d+', p.name))
    if len(candidates) != 1:
        raise ValueError(f"{sample_path}: expected one extracted 20WS serial directory, found {candidates}")
    return candidates[0]


def read_yields(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or not {'Sensor', 'Final_Status'}.issubset(fields):
            raise ValueError(f"{path}: expected unique columns including Sensor and Final_Status")
        if {'wafer_serial_number', 'wafer_name', 'Test'} & set(fields):
            raise ValueError(f"{path}: expected a per-wafer table, not a collected table")
        rows = {}
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{line}: row does not match CSV header")
            sensor = int(row['Sensor'])
            if sensor not in range(1, 53) or sensor in rows:
                raise ValueError(f"{path}:{line}: invalid or duplicate sensor {sensor}")
            row['Sensor'] = str(sensor)
            row['Final_Status'] = row['Final_Status'].strip()
            if row['Final_Status'] not in GRADES:
                raise ValueError(f"{path}:{line}: unknown Final_Status {row['Final_Status']!r}")
            rows[sensor] = row
    if not rows:
        raise ValueError(f"{path}: empty sensor yield table")
    return fields, rows
