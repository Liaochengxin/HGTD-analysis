#!/usr/bin/env python3
"""Draw Sensor Grading Maps from IME sensorYield.csv files.

The layout follows ``2nd_batch_results/B23_1/Sensor_Grade_Map.png``.  Each
input table must contain exactly one row for every sensor from 1 to 52.

Usage:
    python3 HGTD-analysis/scirpt/plot_sensor_grade_maps.py

By default, this draws B23-19 and B23-25.  To draw other wafers, pass one or
more ``--wafer NAME=CSV_PATH`` options, for example:

    python3 HGTD-analysis/scirpt/plot_sensor_grade_maps.py \
        --wafer B31-14=2nd_batch_95/B31-14/sensorYield.csv \
        --wafer B31-15=2nd_batch_95/B31-15/sensorYield.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = {
    "B23-19": REPOSITORY_ROOT / "CQC_sample/CERN/2nd_batch_95/B23_19/sensorYields.csv",
    "B23-25": REPOSITORY_ROOT / "CQC_sample/CERN/2nd_batch_95/B23_25/sensorYields.csv",
}
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "sensor_grade_maps"
EXPECTED_SENSORS = set(range(1, 53))

# Row 0 is the top row.  The numbering follows the serpentine placement in
# the B23_1 reference map; positions not listed are intentionally blank.
SENSOR_POSITIONS = {
    sensor: (row, column)
    for row, sensors in enumerate(
        (
            (None, None, 1, 2, 3, 4, None, None),
            (None, 10, 9, 8, 7, 6, 5, None),
            (11, 12, 13, 14, 15, 16, 17, 18),
            (26, 25, 24, 23, 22, 21, 20, 19),
            (27, 28, 29, 30, 31, 32, 33, 34),
            (42, 41, 40, 39, 38, 37, 36, 35),
            (None, 43, 44, 45, 46, 47, 48, None),
            (None, None, 52, 51, 50, 49, None, None),
        )
    )
    for column, sensor in enumerate(sensors)
    if sensor is not None
}

# Keep the map close to the supplied reference: grades are displayed as text;
# a restrained tint helps compare grades at a glance without obscuring labels.
GRADE_COLOURS = {
    "A": "#eaf5ea",
    "B": "#fff4d6",
    "B1": "#fff4d6",
    "B2": "#fff4d6",
    "C": "#fde8e7",
}


def read_grades(csv_path: Path) -> dict[int, str]:
    """Read and validate one yield table, returning sensor -> Final_Status."""
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required_columns = {"Sensor", "Final_Status"}
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                f"{csv_path} must contain columns: {', '.join(sorted(required_columns))}"
            )

        grades: dict[int, str] = {}
        for line_number, row in enumerate(reader, start=2):
            try:
                sensor = int(row["Sensor"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"{csv_path}:{line_number}: invalid Sensor value") from error
            if sensor in grades:
                raise ValueError(f"{csv_path}:{line_number}: duplicated sensor {sensor}")

            grade = (row["Final_Status"] or "").strip()
            if not grade:
                raise ValueError(f"{csv_path}:{line_number}: missing Final_Status for sensor {sensor}")
            grades[sensor] = grade

    if set(grades) != EXPECTED_SENSORS:
        missing = sorted(EXPECTED_SENSORS - set(grades))
        unexpected = sorted(set(grades) - EXPECTED_SENSORS)
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unexpected:
            details.append(f"unexpected {unexpected}")
        raise ValueError(f"{csv_path}: expected sensors 1--52 ({'; '.join(details)})")
    return grades


def draw_grade_map(wafer: str, grades: dict[int, str], output_path: Path) -> None:
    """Render the fixed sensor layout and save it as a PNG."""
    figure, axis = plt.subplots(figsize=(8, 7.75), dpi=160)
    axis.set_xlim(0, 8)
    axis.set_ylim(8, 0)
    axis.set_aspect("equal")
    axis.set_title(f"Sensor Grading Map — {wafer}", fontsize=24, pad=28)

    for row in range(8):
        for column in range(8):
            sensor = next(
                (number for number, position in SENSOR_POSITIONS.items() if position == (row, column)),
                None,
            )
            colour = GRADE_COLOURS.get(grades[sensor], "#ffffff") if sensor else "#ffffff"
            axis.add_patch(
                Rectangle(
                    (column, row), 1, 1, facecolor=colour, edgecolor="black", linewidth=0.7, linestyle=":"
                )
            )
            if sensor is not None:
                axis.text(column + 0.5, row + 0.36, str(sensor), ha="center", va="center", fontsize=13)
                axis.text(
                    column + 0.5,
                    row + 0.70,
                    grades[sensor],
                    ha="center",
                    va="center",
                    fontsize=10,
                )

    axis.set_xticks(range(9))
    axis.set_yticks(range(9))
    axis.set_xticklabels([])
    axis.set_yticklabels([])
    axis.tick_params(axis="both", which="both", direction="in", top=False, right=False)
    axis.set_xticks([value / 10 for value in range(81)], minor=True)
    axis.set_yticks([value / 10 for value in range(81)], minor=True)
    axis.tick_params(axis="both", which="minor", length=5, bottom=True, left=True, top=False, right=False)

    grade_counts = Counter(grades.values())
    summary = ", ".join(f"{grade}: {count}" for grade, count in sorted(grade_counts.items()))
    figure.text(0.5, 0.035, f"Final_Status counts — {summary}", ha="center", fontsize=11)
    figure.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.88)
    figure.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def compare_grades(left: dict[int, str], right: dict[int, str]) -> list[int]:
    """Return sensor IDs whose Final_Status differs between the two tables."""
    return [sensor for sensor in sorted(EXPECTED_SENSORS) if left[sensor] != right[sensor]]


def parse_wafer_argument(value: str) -> tuple[str, Path]:
    """Parse a ``NAME=CSV_PATH`` command-line wafer specification."""
    wafer, separator, csv_path = value.partition("=")
    if not separator or not wafer or not csv_path:
        raise argparse.ArgumentTypeError("use the form NAME=CSV_PATH")
    return wafer, Path(csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wafer",
        action="append",
        type=parse_wafer_argument,
        metavar="NAME=CSV_PATH",
        help="Wafer name and IME sensorYield.csv path; repeat for multiple wafers.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    inputs = dict(arguments.wafer) if arguments.wafer else DEFAULT_INPUTS
    grades_by_wafer = {wafer: read_grades(path) for wafer, path in inputs.items()}

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    for wafer, grades in grades_by_wafer.items():
        output_path = arguments.output_dir / f"{wafer}_Sensor_Grade_Map.png"
        draw_grade_map(wafer, grades, output_path)
        print(f"Wrote {output_path}")

    if len(grades_by_wafer) == 2:
        left_name, right_name = grades_by_wafer
        mismatched_sensors = compare_grades(grades_by_wafer[left_name], grades_by_wafer[right_name])
        if mismatched_sensors:
            print(
                f"{left_name} and {right_name} Final_Status values differ for "
                f"{len(mismatched_sensors)} sensor(s): {mismatched_sensors}"
            )
        else:
            print(f"{left_name} and {right_name} Final_Status values are identical for all 52 sensors.")


if __name__ == "__main__":
    main()
