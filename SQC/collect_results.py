#!/usr/bin/env python3
"""Collect SQC crosscheck.csv files using each batch's sensor_plan.csv.

INPUT_DIR may be a batch, site, or results root. Identity includes the
relative batch path, production batch and sensor. Missing/duplicate manifest
identities and invalid result groups fail before writing. Planned sensors
without a crosscheck are reported so partial cluster runs remain reviewable.
"""

import argparse
import csv
import math
import re
from pathlib import Path

DEFAULT_ROOT = None
METRICS = ['Mean', 'RMS', 'VbdMin', 'RMS/Mean', 'IRatio', 'LKGMin', 'LKGMax', 'Valid']
GROUPS = {'ProbeCard', 'Needle', 'Needle(inner)', 'Needle(inner2)'}
FIELDS = ['batch', 'output_group', 'output_sensor', 'label', 'Tp', 'Tn', 'cqc', 'Group', *METRICS]


def read_manifest(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not {'output_group', 'output_sensor', 'label', 'Tp', 'Tn', 'cqc'}.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: missing sensor-plan columns')
        manifest = {}
        for row in reader:
            key = (row['output_group'], row['output_sensor'])
            if not re.fullmatch(r'B\d+', key[0]) or not re.fullmatch(r'W\d+-P\d+', key[1]):
                raise ValueError(f'{path}: invalid sensor identity {key}')
            if key in manifest:
                raise ValueError(f'{path}: duplicate sensor identity {key}')
            if any(not math.isfinite(float(row[field])) for field in ('Tp', 'Tn')):
                raise ValueError(f'{path}: non-finite temperature for {key}')
            manifest[key] = row
    return manifest


def read_crosscheck(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['Group', *METRICS]:
            raise ValueError(f'{path}: unexpected crosscheck columns')
        rows = list(reader)
    groups = [row['Group'] for row in rows]
    if len(groups) != len(set(groups)) or not {'ProbeCard', 'Needle'}.issubset(groups) or not set(groups).issubset(GROUPS):
        raise ValueError(f'{path}: missing, duplicate or unknown result groups')
    for row in rows:
        for field in METRICS:
            value = row[field]
            if field == 'RMS/Mean':
                if not value.endswith('%'):
                    raise ValueError(f'{path}: RMS/Mean must have a percent suffix')
                value = value[:-1]
            if not math.isfinite(float(value)):
                raise ValueError(f'{path}: non-finite {field}')
        valid = float(row['Valid'])
        maximum = 15 if row['Group'] == 'ProbeCard' else 225
        if not valid.is_integer() or not 0 <= valid <= maximum:
            raise ValueError(f'{path}: invalid Valid count for {row["Group"]}')
    return rows


def collect_summary(root, output=None):
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f'results directory does not exist: {root}')
    files = sorted(root.rglob('crosscheck.csv'))
    if not files:
        raise ValueError(f'no crosscheck.csv files under {root}')
    plans = {}
    seen = set()
    rows = []
    for path in files:
        batch = path.parent.parent.parent
        key = (path.parent.parent.name, path.parent.name)
        if batch not in plans:
            plans[batch] = read_manifest(batch / 'sensor_plan.csv')
        if key not in plans[batch]:
            raise ValueError(f'{path}: sensor {key} absent from {batch / "sensor_plan.csv"}')
        identity = (batch, *key)
        if identity in seen:
            raise ValueError(f'{path}: duplicate result identity {identity}')
        seen.add(identity)
        meta = plans[batch][key]
        batch_name = batch.relative_to(root).as_posix() if batch != root else root.name
        for row in read_crosscheck(path):
            rows.append({'batch': batch_name, **{field: meta[field] for field in
                         ('output_group', 'output_sensor', 'label', 'Tp', 'Tn', 'cqc')}, **row})
    # Also include entirely unfinished batches in the completeness report.
    for manifest in sorted(root.rglob('sensor_plan.csv')):
        if manifest.parent not in plans:
            plans[manifest.parent] = read_manifest(manifest)
    missing = [(batch / group / sensor).relative_to(root).as_posix()
               for batch, plan in plans.items() for group, sensor in plan
               if (batch, group, sensor) not in seen]
    target = output or root / 'summary_all.csv'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'{target}: {len(rows)} rows from {len(files)} sensors; missing planned sensors={len(missing)}')
    for sensor in missing:
        print(f'[missing] {sensor}')
    return target, len(files), missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path, nargs='?', default=DEFAULT_ROOT)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    if args.input_dir is None:
        parser.error('input_dir is required (select an SQC batch, site or results root)')
    try:
        collect_summary(Path(args.input_dir), args.output.expanduser() if args.output else None)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
