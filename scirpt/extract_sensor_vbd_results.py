#!/usr/bin/env python3
"""Extract per-channel CQC or per-pad SQC Vbd data.

CQC ROOT mode reads ChannelResults and writes probe_card_channels.csv.
SQC ROOT mode exports the 225 individual pixel results to pixel_vbd.csv
and the embedded 15 CQC channels to matched_cqc_channels.csv. Values are
already corrected to 20 degC and are exported without recalculation or cuts.
--input-format log selects the historical CQC run.log parser.
--input-format raw selects the historical SQC summed-current calculation.

SQC raw mode reads the 225 pixel IV files for each sensor, sums the 15 pixels in
each pad, finds the 7.5 uA crossing, and writes the measured 20 degC Vbd to
``pad_vbd.csv`` beside ``SweepVoltage0``. It applies no temperature correction.
The pad grouping follows
``process_perpad.C``: pad N contains pixels N, N+15, ..., N+210.

Usage from the repository root::

    python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py --source CQC \
        CQC_results/CERN/2nd_batch_95_IHEP

    python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py --source SQC \
        SQC_results/CERN/2nd_batch

    python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py --source SQC \
        --input-format raw SQC_sample/2nd_batch_SQC
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "CQC"))
from yield_tables import find_yield_file, read_yields


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
WAFER_DIR_RE = re.compile(r"B(?P<batch>\d+)_(?P<wafer>\d+)")
SQC_SENSOR_DIR_RE = re.compile(r"W(?P<wafer>\d+)_P(?P<sensor_location>\d+)")
VBD_RE = re.compile(
    rf"^\s*(?P<record_type>NEW|SHORT)\s+Sensor\s+(?P<sensor>\d+)"
    rf"\s+col\s+(?P<channel>\d+)\s+raw=\s*(?P<raw>{NUMBER})\s*V"
    rf"\s+T=\s*(?P<temperature>{NUMBER})\s*°C"
    rf"\s+corr=\s*(?P<corrected>{NUMBER})\s*V\b"
)
LEAKAGE_RE = re.compile(
    rf"^\s*Sensor\s+(?P<sensor>\d+)\s+col\s+(?P<channel>\d+)"
    rf"\s+Vprobe\s*=\s*(?P<voltage>{NUMBER})\s*V"
    rf"\s+Itotal\s*=\s*(?P<current>{NUMBER})\s*A\b"
)

FIELDS = [
    "sensor_location",
    "channel",
    "sensor_class",
    "vbd_20C_V",
    "leakage_current_A",
]
SQC_FIELDS = ["sensor_location", "pad", "vbd_20C_V", "n_pixels"]
N_CHANNELS = 15
N_PIXELS = 225
SQC_PAD_CURRENT_UA = 7.5


def read_sensor_classes(path: Path) -> dict[int, str]:
    if not path.is_file():
        raise ValueError(f"missing class table: {path}")

    classes: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "Sensor" not in reader.fieldnames:
            raise ValueError(f"{path} has no Sensor column")
        if "Final_Status" not in reader.fieldnames:
            raise ValueError(f"{path} has no Final_Status column")
        for row in reader:
            sensor_text = (row.get("Sensor") or "").strip()
            if not sensor_text:
                continue
            sensor = int(sensor_text)
            if sensor in classes:
                raise ValueError(f"duplicate Sensor={sensor} in {path}")
            classes[sensor] = (row.get("Final_Status") or "").strip()
    return classes


def parse_log(path: Path):
    vbd_by_channel: dict[tuple[int, int], dict[str, str]] = {}
    leakage_by_channel: dict[tuple[int, int], dict[str, str]] = {}

    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            match = VBD_RE.match(line)
            if match:
                values = match.groupdict()
                key = (int(values["sensor"]), int(values["channel"]))
                if key in vbd_by_channel:
                    raise ValueError(
                        f"duplicate Vbd log entry for Sensor {key[0]}, "
                        f"channel {key[1]} at {path}:{line_number}"
                    )
                vbd_by_channel[key] = values
                continue

            match = LEAKAGE_RE.match(line)
            if match:
                values = match.groupdict()
                key = (int(values["sensor"]), int(values["channel"]))
                if key in leakage_by_channel:
                    raise ValueError(
                        f"duplicate leakage log entry for Sensor {key[0]}, "
                        f"channel {key[1]} at {path}:{line_number}"
                    )
                leakage_by_channel[key] = values

    return vbd_by_channel, leakage_by_channel


def extract_wafer(run_log: Path) -> tuple[Path, int, int, int]:
    wafer_dir = run_log.parent
    wafer_match = WAFER_DIR_RE.fullmatch(wafer_dir.name)
    if wafer_match is None:
        raise ValueError(f"wafer directory must be named B<batch>_<wafer>: {wafer_dir}")

    classes = read_sensor_classes(find_yield_file(wafer_dir))
    vbd_by_channel, leakage_by_channel = parse_log(run_log)

    sensors = sorted(set(classes)
                     | {sensor for sensor, _ in vbd_by_channel}
                     | {sensor for sensor, _ in leakage_by_channel})
    if not sensors:
        raise ValueError(f"no sensors found in {run_log}")

    output_path = wafer_dir / "probe_card_channels.csv"
    missing_vbd = 0
    missing_leakage = 0
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for sensor in sensors:
            for channel in range(1, 16):
                key = (sensor, channel)
                vbd = vbd_by_channel.get(key)
                leakage = leakage_by_channel.get(key)
                missing_vbd += vbd is None
                missing_leakage += leakage is None
                writer.writerow({
                    "sensor_location": sensor,
                    "channel": channel,
                    "sensor_class": classes.get(sensor, ""),
                    "vbd_20C_V": vbd["corrected"] if vbd else "",
                    "leakage_current_A": leakage["current"] if leakage else "",
                })

    return output_path, len(sensors), missing_vbd, missing_leakage


def read_pixel_iv(path: Path) -> list[tuple[float, float]] | None:
    """Read one SQC pixel IV as (absolute voltage, absolute current) points."""
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            if not header:
                return None
            voltage_column = next(
                (index for index, name in enumerate(header)
                 if "voltage" in name.lower()), None
            )
            current_column = next(
                (index for index, name in enumerate(header)
                 if "current" in name.lower() and "meas" not in name.lower()), None
            )
            if voltage_column is None or current_column is None:
                return None

            points = []
            for row in reader:
                if len(row) <= max(voltage_column, current_column):
                    continue
                try:
                    points.append((abs(float(row[voltage_column])),
                                   abs(float(row[current_column]))))
                except ValueError:
                    continue
            return points or None
    except OSError:
        return None


def find_pixel_file(sweep_dir: Path, pixel_index: int) -> Path | None:
    """Prefer a numbered duplicate (the tested file) over the base filename."""
    base_name = f"1-{pixel_index}.csv"
    numbered = []
    pattern = re.compile(rf"1-{pixel_index}\((\d+)\)\.csv")
    for candidate in sweep_dir.glob(f"1-{pixel_index}*.csv"):
        match = pattern.fullmatch(candidate.name)
        if match:
            numbered.append((int(match.group(1)), candidate))

    if len(numbered) > 1:
        names = ", ".join(path.name for _, path in sorted(numbered))
        raise ValueError(f"multiple numbered files for pixel {pixel_index}: {names}")
    if numbered:
        numbered_path = numbered[0][1]
        base_path = sweep_dir / base_name
        if base_path.is_file():
            print(f"  [warn] using {numbered_path.name} over duplicate {base_name}")
        return numbered_path

    base_path = sweep_dir / base_name
    return base_path if base_path.is_file() else None


def pad_vbd_at_20c(curves: list[list[tuple[float, float]]]) -> float | None:
    """Sum 15 pixel curves and interpolate the first 7.5 uA crossing."""
    if len(curves) != N_CHANNELS or not curves[0]:
        return None

    voltage_order = [voltage for voltage, _ in curves[0]]
    currents_by_curve = []
    for curve in curves:
        currents = {}
        for voltage, current in curve:
            if voltage in currents:
                raise ValueError(f"duplicate voltage point {voltage:g} V in SQC IV curve")
            currents[voltage] = current
        currents_by_curve.append(currents)

    total_points = []
    for voltage in voltage_order:
        if all(voltage in currents for currents in currents_by_curve):
            total_points.append((voltage, sum(c[voltage] for c in currents_by_curve)))

    threshold = SQC_PAD_CURRENT_UA * 1e-6
    for (v_lo, i_lo), (v_hi, i_hi) in zip(total_points, total_points[1:]):
        if i_lo < threshold < i_hi:
            return v_lo + (v_hi - v_lo) * (threshold - i_lo) / (i_hi - i_lo)
    return None


def extract_sqc_sensor(sensor_dir: Path) -> tuple[Path, int, int]:
    """Write one 15-row pad Vbd table for an SQC sensor input directory."""
    match = SQC_SENSOR_DIR_RE.fullmatch(sensor_dir.name)
    if match is None:
        raise ValueError(f"SQC sensor directory must be named W<wafer>_P<location>: {sensor_dir}")
    sensor_location = int(match.group("sensor_location"))
    sweep_dir = sensor_dir / "SweepVoltage0"
    if not sweep_dir.is_dir():
        raise ValueError(f"missing SQC input directory: {sweep_dir}")

    output_path = sensor_dir / "pad_vbd.csv"
    missing_vbd = 0
    incomplete_pads = 0
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SQC_FIELDS)
        writer.writeheader()
        for pad in range(1, N_CHANNELS + 1):
            pixel_indices = range(pad, N_PIXELS + 1, N_CHANNELS)
            curves = [
                read_pixel_iv(pixel_file)
                for index in pixel_indices
                if (pixel_file := find_pixel_file(sweep_dir, index)) is not None
            ]
            valid_curves = [curve for curve in curves if curve is not None]
            vbd = (pad_vbd_at_20c(valid_curves)
                   if len(valid_curves) == N_CHANNELS else None)
            missing_vbd += vbd is None
            incomplete_pads += len(valid_curves) != N_CHANNELS
            writer.writerow({
                "sensor_location": sensor_location,
                "pad": pad,
                "vbd_20C_V": f"{vbd:.6f}" if vbd is not None else "",
                "n_pixels": len(valid_curves),
            })

    return output_path, missing_vbd, incomplete_pads


def extract_sqc_root(root: Path) -> int:
    sensor_dirs = sorted(
        path for path in root.glob("B*/W*_P*")
        if path.is_dir() and SQC_SENSOR_DIR_RE.fullmatch(path.name)
    )
    sensor_dirs = [path for path in sensor_dirs if (path / "SweepVoltage0").is_dir()]
    if not sensor_dirs:
        raise ValueError(f"no B<batch>/W<wafer>_P<location>/SweepVoltage0 inputs found under {root}")

    failures = 0
    for sensor_dir in sensor_dirs:
        try:
            output, missing_vbd, incomplete_pads = extract_sqc_sensor(sensor_dir)
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[error] {error}", file=sys.stderr)
            continue
        print(
            f"{output}: 15 pads; missing Vbd={missing_vbd}, "
            f"incomplete pads={incomplete_pads}"
        )
    return 1 if failures else 0


def read_result_tree(path: Path, tree_name: str, fields: list[str],
                     id_limits: dict[str, int]) -> list[dict]:
    """Read saved measurements, validating identities independently of Vbd cuts."""
    import uproot

    with uproot.open(path) as root_file:
        if tree_name not in root_file:
            raise ValueError(f"{path}: missing TTree {tree_name}")
        tree = root_file[tree_name]
        missing = set(fields) - set(tree.keys())
        if missing:
            raise ValueError(f"{path}: {tree_name} missing branches {sorted(missing)}")
        arrays = {field: tree[field].array(library="np") for field in fields}
    lengths = {len(array) for array in arrays.values()}
    if len(lengths) != 1 or not next(iter(lengths)):
        raise ValueError(f"{path}: empty or inconsistent {tree_name} branches")
    rows = []
    seen = set()
    for values in zip(*(arrays[field] for field in fields)):
        row = dict(zip(fields, values))
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError(f"{path}: non-finite value in {tree_name}")
        for field, maximum in id_limits.items():
            value = float(row[field])
            if not value.is_integer() or not 1 <= value <= maximum:
                raise ValueError(f"{path}: invalid {field}={value}")
            row[field] = int(value)
        key = tuple(row[field] for field in id_limits)
        if key in seen:
            raise ValueError(f"{path}: duplicate {tree_name} identity {key}")
        seen.add(key)
        rows.append(row)
    return rows


def extract_result_root(path: Path, source: str, output_dir: Path | None = None) -> list[Path]:
    """Prepare and validate all tables before writing a sensor/wafer export."""
    target = output_dir or path.parent
    tables = []
    if source == "CQC":
        if WAFER_DIR_RE.fullmatch(path.parent.name) is None:
            raise ValueError(f"expected ROOT file in B<batch>_<wafer>: {path}")
        _, classes = read_yields(find_yield_file(path.parent))
        rows = read_result_tree(path, "ChannelResults",
                                ["sensor_id", "channel_id", "vbd_corrected_20C_V", "leakage_current_A"],
                                {"sensor_id": 52, "channel_id": 15})
        exported = []
        for row in rows:
            sensor = row["sensor_id"]
            if sensor not in classes:
                raise ValueError(f"{path}: Sensor {sensor} absent from yield table")
            exported.append({"sensor_location": sensor, "channel": row["channel_id"],
                             "sensor_class": classes[sensor]["Final_Status"],
                             "vbd_20C_V": row["vbd_corrected_20C_V"],
                             "leakage_current_A": row["leakage_current_A"]})
        tables.append(("probe_card_channels.csv", FIELDS, exported))
    else:
        if re.fullmatch(r"W\d+-P\d+", path.parent.name) is None:
            raise ValueError(f"expected ROOT file in W<wafer>-P<location>: {path}")
        for tree, id_field, maximum, name in (
            ("SQC_results", "pad_position", 225, "pixel_vbd.csv"),
            ("CQC_results", "channel_id", 15, "matched_cqc_channels.csv"),
        ):
            fields = [id_field, "vbd_corrected_20C_V", "leakage_current_A"]
            rows = read_result_tree(path, tree, fields, {id_field: maximum})
            tables.append((name, fields, rows))
    target.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, fields, rows in tables:
        output = target / name
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{output}: {len(rows)} rows")
        outputs.append(output)
    return outputs


def export_results(root: Path, source: str, output_dir: Path | None) -> int:
    files = [root] if root.is_file() else sorted(
        path for path in root.rglob("*.root")
        if (WAFER_DIR_RE.fullmatch(path.parent.name) if source == "CQC"
            else re.fullmatch(r"W\d+-P\d+", path.parent.name))
    )
    if not files:
        raise ValueError(f"no {source} per-wafer/per-sensor ROOT results under {root}")
    # One saved result file per identity; never overwrite with another ROOT file.
    if len({path.parent for path in files}) != len(files):
        raise ValueError("multiple ROOT files for one wafer/sensor directory")
    failures = 0
    for path in files:
        target = (output_dir / path.parent.relative_to(root) if output_dir and root.is_dir()
                  else output_dir)
        try:
            extract_result_root(path, source, target)
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[error] {error}", file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=("CQC", "SQC"),
        default="CQC",
        help="measurement source (default: CQC)",
    )
    parser.add_argument("--input-format", choices=("root", "log", "raw"), default="root",
                        help="root: saved results (default); log: CQC legacy; raw: SQC summed IV")
    parser.add_argument("--output-dir", type=Path,
                        help="ROOT export directory; retains paths relative to results_dir")
    parser.add_argument(
        "results_dir",
        type=Path,
        help="results directory or one ROOT file; raw mode takes an SQC sample batch",
    )
    args = parser.parse_args()

    root = args.results_dir.expanduser()
    if args.input_format == "root":
        if not root.exists():
            parser.error(f"results path does not exist: {root}")
        try:
            return export_results(root, args.source,
                                  args.output_dir.expanduser() if args.output_dir else None)
        except (OSError, ValueError, ImportError) as error:
            parser.error(str(error))
    if args.output_dir:
        parser.error("--output-dir is supported only for ROOT exports")
    if (args.input_format, args.source) not in (("log", "CQC"), ("raw", "SQC")):
        parser.error("log mode requires --source CQC; raw mode requires --source SQC")
    if not root.is_dir():
        parser.error(f"results directory does not exist: {root}")

    if args.source == "SQC":
        return extract_sqc_root(root)

    run_logs = sorted(
        path for path in root.rglob("run.log")
        if WAFER_DIR_RE.fullmatch(path.parent.name)
    )
    if not run_logs:
        parser.error(f"no B<batch>_<wafer>/run.log files found under {root}")

    failures = 0
    for run_log in run_logs:
        try:
            output, sensors, missing_vbd, missing_leakage = extract_wafer(run_log)
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[error] {error}", file=sys.stderr)
            continue
        print(
            f"{output}: {sensors * 15} rows; "
            f"missing Vbd={missing_vbd}, missing leakage={missing_leakage}"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
