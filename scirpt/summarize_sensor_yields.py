#!/usr/bin/env python3
"""Count per-wafer A/B/C yields from collected IHEP and optional IME tables.

BASE_DIR holds sensor_yields_by_grade/ and/or sensor_yields_by_grade_IME/.
Relative paths are rooted on CERN EOS; --output selects the summary directory.
Duplicate sensor identities and mismatched comparison sets are errors.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CQC'))
from yield_tables import GRADES, resolve_path, wafer_key, wafer_name


def summarize(base_path, output_path=None):
    counts = Counter()
    identities = {}
    for test, folder in (('IME', 'sensor_yields_by_grade_IME'), ('IHEP', 'sensor_yields_by_grade')):
        directory = base_path / folder
        if not directory.is_dir():
            continue
        seen = set()
        for grade in ('A', 'B', 'C'):
            path = directory / f'{grade}.csv'
            with path.open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                if not {'wafer_name', 'Sensor', 'Final_Status'}.issubset(reader.fieldnames or []):
                    raise ValueError(f'{path}: missing wafer_name, Sensor or Final_Status')
                for line, row in enumerate(reader, 2):
                    name = wafer_name(row['wafer_name'])
                    sensor = int(row['Sensor'])
                    key = (name, sensor)
                    if sensor not in range(1, 53) or key in seen:
                        raise ValueError(f'{path}:{line}: invalid or duplicate sensor {key}')
                    if GRADES.get(row['Final_Status']) != grade:
                        raise ValueError(f'{path}:{line}: status does not belong in grade {grade}')
                    seen.add(key)
                    counts[grade, test, name] += 1
        if not seen:
            raise ValueError(f'{directory}: no sensor rows')
        identities[test] = seen
    if not identities:
        raise ValueError(f'no sensor_yields_by_grade* directories under {base_path}')
    if len(identities) == 2 and identities['IME'] != identities['IHEP']:
        raise ValueError('IME and IHEP wafer/sensor sets differ; select matching batches')
    wafers = {name for items in identities.values() for name, _ in items}
    target = output_path or base_path / 'yield_summary'
    target.mkdir(parents=True, exist_ok=True)
    for grade in ('A', 'B', 'C'):
        with (target / f'{grade}.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['wafer', *identities])
            for name in sorted(wafers, key=wafer_key):
                writer.writerow([name, *[counts[grade, test, name] for test in identities]])
            writer.writerow(['Total', *[sum(counts[grade, test, name] for name in wafers)
                                       for test in identities]])
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        print(summarize(resolve_path(args.base_dir), resolve_path(args.output) if args.output else None))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
