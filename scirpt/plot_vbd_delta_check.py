#!/usr/bin/env python3
"""Plot per-sensor Vbd deltas of IME yield tables against a reference wafer.

A flat delta line with zero scatter shows that the delivered table for a
wafer was generated from the reference wafer's data with only the
temperature parameter changed (wrong input CSV), not from an independent
measurement.  The dashed line marks the offset predicted from the wafer
temperature table, -(dT) x 1.1 V/degC.

Usage:
    python3 HGTD-analysis/scirpt/plot_vbd_delta_check.py

    # Custom pairs or column:
    python3 HGTD-analysis/scirpt/plot_vbd_delta_check.py \
        --base B23-16 --wafers B23-19 B23-25 --column Vbd_Min
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPOSITORY_ROOT / "CQC_sample/CERN/2nd_batch_95"
TEMPERATURE_TABLE = SAMPLE_DIR / "wafer_temperature_template.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "vbd_delta_checks"
VBD_TCR = 1.1  # V/degC, 20 degC correction slope used by the CQC analysis

# Reference palette (light mode): series blue, chrome greys.
SERIES = "#2a78d6"
SERIES_DARK = "#1c5cab"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"


def parse_wafer(name: str) -> tuple[int, int]:
    """'B23-19' or 'B23_19' -> (23, 19)."""
    batch, wafer = name.replace("_", "-").lstrip("Bb").split("-")
    return int(batch), int(wafer)


def serial_of(name: str) -> str:
    batch, wafer = parse_wafer(name)
    return f"20WS001{batch:02d}{wafer:05d}"


def load_temperatures() -> dict[str, float]:
    with TEMPERATURE_TABLE.open(encoding="utf-8-sig", errors="replace", newline="") as file:
        return {row[0]: float(row[1]) for row in list(csv.reader(file))[1:] if row}


def find_yield_file(wafer: str) -> Path:
    """Locate the per-sensor yield table regardless of its delivered name
    (sensorYield.csv / sensorYields.csv / <serial>.csv), by header content."""
    wafer_dir = next(
        path for path in (SAMPLE_DIR / wafer, SAMPLE_DIR / wafer.replace("-", "_")) if path.exists()
    )
    for candidate in sorted(wafer_dir.glob("*.csv")):
        with candidate.open(encoding="utf-8-sig", errors="replace", newline="") as file:
            header = csv.reader(file).__next__()
        if "Sensor" in header and "Final_Status" in header:
            return candidate
    raise SystemExit(f"no sensor yield table found in {wafer_dir}")


def read_vbd(wafer: str, column: str) -> dict[int, float]:
    yield_file = find_yield_file(wafer)
    with yield_file.open(encoding="utf-8-sig", errors="replace", newline="") as file:
        table = {int(row["Sensor"]): float(row[column]) for row in csv.DictReader(file) if row.get("Sensor")}
    if not table:
        raise SystemExit(f"no rows with column {column!r} in {yield_file}")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="B23-16", help="reference wafer")
    parser.add_argument("--wafers", nargs="+", default=["B23-19", "B23-25"], help="delivered wafers to check")
    parser.add_argument("--column", default="Vbd_Average", help="sensorYield.csv column to diff")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    temperatures = load_temperatures()
    base_values = read_vbd(args.base, args.column)
    base_temp = temperatures[serial_of(args.base)]

    wafers = args.wafers
    fig, axes = plt.subplots(
        len(wafers), 1, figsize=(8, 2.8 * len(wafers)), sharex=True, sharey=True, dpi=200
    )
    axes = axes if len(wafers) > 1 else [axes]

    pad = 0.25
    loaded = [(wafer, read_vbd(wafer, args.column)) for wafer in wafers]
    all_deltas = [v[s] - base_values[s] for _, v in loaded for s in base_values if s in v]
    y_min, y_max = min(all_deltas) - pad, max(all_deltas) + pad

    for ax, (wafer, values) in zip(axes, loaded):
        sensors = sorted(set(base_values) & set(values))
        deltas = [values[s] - base_values[s] for s in sensors]

        mean, std = statistics.mean(deltas), statistics.pstdev(deltas)
        temp = temperatures[serial_of(wafer)]
        predicted = -(temp - base_temp) * VBD_TCR

        ax.axhline(0, color=BASELINE, linewidth=1, zorder=1)
        ax.axhline(predicted, color=INK_SECONDARY, linewidth=1.2, linestyle="--", zorder=2)
        ax.axhline(mean, color=SERIES_DARK, linewidth=1, zorder=2)
        ax.plot(sensors, deltas, "o", color=SERIES, markersize=4.5, zorder=3)

        ax.set_ylabel(rf"$\Delta$ {args.column} [V]", color=INK_SECONDARY, fontsize=10)
        ax.set_title(
            f"{wafer} $-$ {args.base}   ($\\Delta T$ = {temp - base_temp:+.1f}$\\degree$C)",
            color=INK, fontsize=11, loc="left",
        )
        # Keep the annotation clear of the flat line: place it on whichever
        # side of the axes the line does not occupy.
        frac = (mean - y_min) / (y_max - y_min)
        ax.set_ylim(y_min, y_max)
        ax.text(
            0.012, 0.10 if frac > 0.5 else 0.88,
            f"mean = {mean:+.3f} V,  $\\sigma$ = {std:.3f} V\n"
            f"predicted $-\\Delta T\\times${VBD_TCR} = {predicted:+.3f} V",
            transform=ax.transAxes, fontsize=9.5, color=INK_SECONDARY,
            va="bottom" if frac > 0.5 else "top",
        )
        print(f"{wafer} vs {args.base}: mean = {mean:+.4f} V, sigma = {std:.4f} V, "
              f"predicted = {predicted:+.4f} V")

        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED, labelsize=9)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BASELINE)

    axes[-1].set_xlabel("Sensor", color=INK_SECONDARY, fontsize=10)
    fig.suptitle(
        f"$\\Delta${args.column} per sensor: IME {' / '.join(wafers)} vs IME {args.base}",
        color=INK_SECONDARY, fontsize=11, y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"vbd_delta_{args.column}_{'_'.join(wafers)}_vs_{args.base}.png"
    fig.savefig(output, facecolor="white", bbox_inches="tight")
    print(f"figure -> {output}")


if __name__ == "__main__":
    main()
