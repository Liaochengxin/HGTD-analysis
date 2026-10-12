#!/usr/bin/env python3
"""Plot SQC Vbd distributions at sensor or pad level.

``sensor-level`` reads the ``Needle(inner)`` row from each sensor's
``crosscheck.csv`` and creates separate average, minimum, and RMS plots.
``pad-level`` reads per-pad corrected Vbd values from one sensor ROOT file.
"""

import argparse
import csv
import math
from pathlib import Path


SENSOR_METRICS = (
    ("Mean", "Vbd average [V]", "vbd_average.pdf"),
    ("VbdMin", "Vbd minimum [V]", "vbd_minimum.pdf"),
    ("RMS", "Vbd RMS [V]", "vbd_rms.pdf"),
)
TREE_NAME = "SQC_results"
VBD_BRANCH = "vbd_corrected_20C_V"


def read_sensor_summaries(input_dir: Path) -> dict[str, list[float]]:
    """Read Needle(inner) Vbd metrics from each sensor crosscheck file."""
    files = sorted(input_dir.rglob("crosscheck.csv"))
    if not files:
        raise FileNotFoundError(f"no crosscheck.csv files found under {input_dir}")

    values = {column: [] for column, _, _ in SENSOR_METRICS}
    required = {"Group", *(column for column, _, _ in SENSOR_METRICS)}
    for path in files:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"{path}: expected columns {sorted(required)}")
            matching_rows = [row for row in reader if row["Group"] == "Needle(inner)"]
            if len(matching_rows) != 1:
                raise ValueError(
                    f"{path}: expected exactly one Group='Needle(inner)' row, "
                    f"found {len(matching_rows)}"
                )
            row = matching_rows[0]
            for column in values:
                try:
                    value = float(row[column])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{path}: invalid {column} value {row[column]!r}") from error
                if not math.isfinite(value):
                    raise ValueError(f"{path}: non-finite {column} value {row[column]!r}")
                values[column].append(value)

    return values


def read_pad_vbd(root_path: Path) -> list[float]:
    """Read corrected Vbd for every SQC pad from a sensor ROOT file."""
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
        raise ValueError(f"cannot read SQC ROOT file {root_path}: {error}") from error

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


def plot_pad_level(values: list[float], output_path: Path) -> None:
    import matplotlib.pyplot as plt
    import mplhep as hep

    hep.style.use("ATLAS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(7.5, 6), constrained_layout=True)
    axis.hist(values, bins="auto", histtype="stepfilled", alpha=0.65)
    axis.set_xlabel("Pad Vbd corrected to 20°C [V]")
    axis.set_ylabel("Number of pads")
    axis.grid(axis="y", alpha=0.25)
    hep.atlas.label("HGTD Internal", data=True, rlabel="", loc=2, ax=axis)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path,
        help="SQC results directory for sensor-level, or one sensor ROOT file for pad-level",
    )
    parser.add_argument(
        "--level", required=True, choices=("sensor-level", "pad-level"),
        help="select data source and plotting path",
    )
    parser.add_argument(
        "-o", "--output", type=Path,
        help="sensor-level: output directory; pad-level: output PDF file",
    )
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve()

    try:
        if args.level == "sensor-level":
            if not input_path.is_dir():
                parser.error(f"sensor-level input must be an SQC results directory: {input_path}")
            values = read_sensor_summaries(input_path)
            output_dir = (
                args.output.expanduser().resolve() if args.output
                else input_path / "vbd_sensor_plots"
            )
            plot_sensor_level(values, output_dir)
            print(f"Collected {len(values['Mean'])} sensor rows from Needle(inner).")
            for _, _, filename in SENSOR_METRICS:
                print(output_dir / filename)
        else:
            if not input_path.is_file():
                parser.error(f"pad-level input must be a sensor ROOT file: {input_path}")
            values = read_pad_vbd(input_path)
            output_path = (
                args.output.expanduser().resolve() if args.output
                else input_path.with_name(f"{input_path.stem}_vbd_pad-level.pdf")
            )
            if output_path.suffix.lower() != ".pdf":
                parser.error("pad-level output must have a .pdf extension")
            plot_pad_level(values, output_path)
            print(f"Plotted {len(values)} pads: {output_path}")
    except (FileNotFoundError, ImportError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
