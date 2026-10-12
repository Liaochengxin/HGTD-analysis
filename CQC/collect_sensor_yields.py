#!/usr/bin/env python3
"""Collect one CQC batch's per-wafer yields into A/B/C tables.

Relative paths are rooted at /eos/user/l/liaoc/public/HGTD_sensor.
--sample selects the matching batch with extracted 20WS serial directories.
--output selects the output parent; --label IME writes sensor_yields_by_grade_IME.
Only the documented B, B1 and B2 statuses are grouped into B.
"""

import argparse
import csv
from pathlib import Path

from yield_tables import GRADES, discover_wafers, find_yield_file, read_yields, resolve_path, wafer_serial


def collect(input_path, sample_path, output_parent, label=None):
    wafers = discover_wafers(input_path)
    samples = discover_wafers(sample_path)
    tables = {grade: [] for grade in ('A', 'B', 'C')}
    fields = []
    for name, path in wafers.items():
        if name not in samples:
            raise ValueError(f"missing sample wafer {name} in {sample_path}")
        serial = wafer_serial(samples[name])
        current_fields, rows = read_yields(find_yield_file(path))
        for field in current_fields:
            if field not in fields:
                fields.append(field)
        for sensor in sorted(rows):
            row = rows[sensor]
            tables[GRADES[row['Final_Status']]].append(
                {'wafer_serial_number': serial, 'wafer_name': name, **row})
    target = output_parent / f"sensor_yields_by_grade{'_' + label if label else ''}"
    target.mkdir(parents=True, exist_ok=True)
    for grade, rows in tables.items():
        with (target / f'{grade}.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, ['wafer_serial_number', 'wafer_name', *fields])
            writer.writeheader()
            writer.writerows(rows)
    return target, {grade: len(rows) for grade, rows in tables.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path)
    parser.add_argument('--sample', type=Path)
    parser.add_argument('--label')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.label and (args.label in ('.', '..') or '/' in args.label or '\\' in args.label):
        parser.error('--label must be a folder suffix, not a path')
    try:
        target, counts = collect(resolve_path(args.input_dir),
                                 resolve_path(args.sample or args.input_dir),
                                 resolve_path(args.output or args.input_dir), args.label)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'{target}: {counts}')


if __name__ == '__main__':
    main()
