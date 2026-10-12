#!/usr/bin/env python3
"""Compare one IHEP batch with IME per-wafer yield tables.

Relative paths are rooted on CERN EOS. Wafer and sensor sets must match;
missing identities are errors rather than silently excluded comparisons.
"""

import argparse
import csv
from pathlib import Path

from yield_tables import discover_wafers, find_yield_file, read_yields, resolve_path, wafer_serial


def compare(ihep_path, ime_path, sample_path, output=None):
    ihep = discover_wafers(ihep_path)
    ime = discover_wafers(ime_path)
    samples = discover_wafers(sample_path)
    if set(ihep) != set(ime):
        raise ValueError(f'wafer sets differ: IHEP-only={sorted(set(ihep)-set(ime))}, '
                         f'IME-only={sorted(set(ime)-set(ihep))}')
    fields = []
    rows = []
    for name in ihep:
        left_fields, left = read_yields(find_yield_file(ihep[name]))
        right_fields, right = read_yields(find_yield_file(ime[name]))
        for field in (*left_fields, *right_fields):
            if field not in fields:
                fields.append(field)
        if set(left) != set(right):
            raise ValueError(f'sensor sets differ for {name}')
        if name not in samples:
            raise ValueError(f'missing sample wafer {name} in {sample_path}')
        prefix = {'wafer_serial_number': wafer_serial(samples[name]), 'wafer_name': name}
        for sensor in sorted(left):
            if left[sensor]['Final_Status'] != right[sensor]['Final_Status']:
                rows.extend([{'Test': 'IHEP', **prefix, **left[sensor]},
                             {'Test': 'IME', **prefix, **right[sensor]}])
    target = output or ihep_path / 'sensor_yield_differences.csv'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, ['Test', 'wafer_serial_number', 'wafer_name', *fields])
        writer.writeheader()
        writer.writerows(rows)
    return target, len(rows) // 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ihep_dir', type=Path)
    parser.add_argument('--ime', required=True, type=Path)
    parser.add_argument('--sample', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        target, count = compare(resolve_path(args.ihep_dir), resolve_path(args.ime),
                                resolve_path(args.sample or args.ime),
                                resolve_path(args.output) if args.output else None)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'{target}: {count} sensors with different statuses')


if __name__ == '__main__':
    main()
