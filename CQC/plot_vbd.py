#!/usr/bin/env python3
"""Plot CQC Vbd distributions at sensor or channel level.

``sensor-level`` reads the per-wafer sensorYield CSV summaries and creates
separate average, minimum, and RMS plots. ``channel-level`` reads corrected
channel Vbd values from one wafer ROOT file and creates one histogram.
"""

import argparse
import math
from pathlib import Path

from yield_tables import find_yield_file, read_yields


SENSOR_METRICS = (
    ("Vbd_Average", "Vbd average [V]", "vbd_average.pdf"),
    ("Vbd_Min", "Vbd minimum [V]", "vbd_minimum.pdf"),
    ("Vbd_Rms", "Vbd RMS [V]", "vbd_rms.pdf"),
)
TREE_NAME = "ChannelResults"
VBD_BRANCH = "vbd_corrected_20C_V"


def read_sensor_summaries(input_dir: Path) -> dict[str, list[float]]:
    """Read per-sensor average, minimum, and RMS values from CQC CSVs."""
    summary_dirs = {
        path.parent
        for filename in ("sensorYield.csv", "sensorYields.csv")
        for path in input_dir.rglob(filename)
    }
    files = [find_yield_file(directory) for directory in sorted(summary_dirs)]
    if not files:
        raise FileNotFoundError(
            f"no sensorYield.csv or sensorYields.csv files found under {input_dir}"
        )

    values = {column: [] for column, _, _ in SENSOR_METRICS}
    required = {"Sensor", *values}
    for path in files:
        fields, rows = read_yields(path)
        if not required.issubset(fields):
            raise ValueError(f"{path}: expected columns {sorted(required)}")
        for sensor, row in rows.items():
            for column in values:
                try:
                    value = float(row[column])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{path}: Sensor {sensor}: invalid {column} {row[column]!r}") from error
                if not math.isfinite(value):
                    raise ValueError(f"{path}: Sensor {sensor}: non-finite {column}")
                values[column].append(value)

    if not values["Vbd_Average"]:
        raise ValueError(f"no sensor rows found in summaries under {input_dir}")
    return values


def read_channel_vbd(root_path: Path) -> list[float]:
    """Read corrected Vbd for every channel from a CQC wafer ROOT file."""
    import uproot

    try:
        with uproot.open(root_path) as root_file:
            if TREE_NAME not in root_file:
                raise ValueError(f"missing {TREE_NAME} TTree")
            tree = root_file[TREE_NAME]
            if VBD_BRANCH not in tree.keys():
                raise ValueError(f"{TREE_NAME} is missing branch {VBD_BRANCH}")
            branch = tree[VBD_BRANCH].array(library="np")
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read CQC ROOT file {root_path}: {error}") from error

    if not len(branch):
        raise ValueError(f"{root_path}: {TREE_NAME} has no entries")
    values = [float(value) for value in branch]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{root_path}: {VBD_BRANCH} contains non-finite values")
    return values


def plot_sensor_level(values: dict[str, list[float]], output_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import mplhep as hep

    hep.style.use("ATLAS")
    output_dir.mkdir(parents=True, exist_ok=True)
    for column, xlabel, filename in SENSOR_METRICS:
        fig, axis = plt.subplots(figsize=(7.5, 6), constrained_layout=True)
        axis.hist(values[column], bins="auto", histtype="stepfilled", alpha=0.65)
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Number of sensors")
        axis.grid(axis="y", alpha=0.25)
        hep.atlas.label("HGTD Internal", data=True, rlabel="", loc=2, ax=axis)
        fig.savefig(output_dir / filename)
        plt.close(fig)


def plot_channel_level(values: list[float], output_path: Path) -> None:
    import matplotlib.pyplot as plt
    import mplhep as hep

    hep.style.use("ATLAS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(7.5, 6), constrained_layout=True)
    axis.hist(values, bins="auto", histtype="stepfilled", alpha=0.65)
    axis.set_xlabel("Channel Vbd corrected to 20°C [V]")
    axis.set_ylabel("Number of channels")
    axis.grid(axis="y", alpha=0.25)
    hep.atlas.label("HGTD Internal", data=True, rlabel="", loc=2, ax=axis)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path,
        help="CQC results directory for sensor-level, or one wafer ROOT file for channel-level",
    )
    parser.add_argument(
        "--level", required=True, choices=("sensor-level", "channel-level"),
        help="select data source and plotting path",
    )
    parser.add_argument(
        "-o", "--output", type=Path,
        help="sensor-level: output directory; channel-level: output PDF file",
    )
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve()

    try:
        if args.level == "sensor-level":
            if not input_path.is_dir():
                parser.error(f"sensor-level input must be a CQC results directory: {input_path}")
            values = read_sensor_summaries(input_path)
            output_dir = (
                args.output.expanduser().resolve() if args.output
                else input_path / "vbd_sensor_plots"
            )
            plot_sensor_level(values, output_dir)
            print(f"Collected {len(values['Vbd_Average'])} sensor rows.")
            for _, _, filename in SENSOR_METRICS:
                print(output_dir / filename)
        else:
            if not input_path.is_file():
                parser.error(f"channel-level input must be a wafer ROOT file: {input_path}")
            values = read_channel_vbd(input_path)
            output_path = (
                args.output.expanduser().resolve() if args.output
                else input_path.with_name(f"{input_path.stem}_vbd_channel-level.pdf")
            )
            if output_path.suffix.lower() != ".pdf":
                parser.error("channel-level output must have a .pdf extension")
            plot_channel_level(values, output_path)
            print(f"Plotted {len(values)} channels: {output_path}")
    except (FileNotFoundError, ImportError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
