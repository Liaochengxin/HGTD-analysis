#!/usr/bin/env python3
"""Compare SQC pad Vbd with the matched CQC channel Vbd in each sensor ROOT file.

The SQC ROOT file has one entry for each of 225 pad positions and a
``CQC_results`` tree with 15 channels. ``--level channel-level`` groups SQC
pads into columns using ``(pad_position - 1) % 15`` and compares each column
with the matching CQC channel. ``--level sensor-level`` compares the minimum
and average over all valid SQC pads with the minimum and average over all
valid CQC channels. The residual convention is SQC - CQC.

Both trees are matched by ``channel_id`` within each sensor ROOT file; no
external CQC input or sensor matching table is needed.

Examples from the repository root::

    python3 HGTD-analysis/scirpt/plot_sqc_cqc_vbd_residuals.py \
        -i SQC_results/CERN/1nd_batch \
        -l channel-level \
        -o HGTD-analysis/scirpt/vbd_residuals

    # Multiple batch/B-level directories are pooled into the same distributions.
    python3 HGTD-analysis/scirpt/plot_sqc_cqc_vbd_residuals.py \
        -i SQC_results/CERN/1nd_batch/B21 SQC_results/CERN/1nd_batch/B22 \
        -l sensor-level \
        -o /tmp/vbd_residuals
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
from scipy.optimize import curve_fit


SQC_SENSOR_RE = re.compile(r"W(?P<wafer>\d+)-P(?P<sensor>\d+)")
SQC_BATCH_RE = re.compile(r"B(?P<batch>\d+)")
SQC_TREE = "SQC_results"
CQC_TREE = "CQC_results"
VBD_BRANCH = "vbd_corrected_20C_V"
VALID_VBD_MIN_V = 165.0
VALID_VBD_MAX_V = 195.0
N_CHANNELS = 15


@dataclass(frozen=True)
class SensorKey:
    batch_group: str
    b_level: int
    wafer: int
    sensor: int

    def label(self) -> str:
        return f"{self.batch_group}/B{self.b_level:02d}/W{self.wafer:02d}-P{self.sensor}"


def discover_root_files(paths: list[Path]) -> list[Path]:
    """Expand input ROOT files/directories, recursively and deterministically."""
    files: set[Path] = set()
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() != ".root":
                raise ValueError(f"input file is not a ROOT file: {path}")
            files.add(path)
        elif path.is_dir():
            files.update(item.resolve() for item in path.rglob("*.root") if item.is_file())
        else:
            raise FileNotFoundError(f"input path does not exist: {path}")
    return sorted(files)


def sqc_sensor_key(path: Path) -> SensorKey:
    """Parse batch/wafer/location from a sensor ROOT file path."""
    sensor_match = SQC_SENSOR_RE.fullmatch(path.parent.name)
    if sensor_match is None:
        sensor_match = SQC_SENSOR_RE.fullmatch(path.stem)
    if sensor_match is None:
        raise ValueError(f"expected SQC sensor path W<wafer>-P<sensor>: {path}")

    production_dir = path.parent.parent
    b_level_match = SQC_BATCH_RE.fullmatch(production_dir.name)
    if b_level_match is None:
        raise ValueError(f"cannot find B<batch> directory above SQC ROOT file: {path}")
    batch_group = production_dir.parent.name
    return SensorKey(
        batch_group=batch_group,
        b_level=int(b_level_match.group("batch")),
        wafer=int(sensor_match.group("wafer")),
        sensor=int(sensor_match.group("sensor")),
    )


def read_tree_arrays(path: Path, tree_name: str, branches: tuple[str, ...]) -> dict[str, np.ndarray]:
    import uproot

    try:
        with uproot.open(path) as root_file:
            if tree_name not in root_file:
                raise ValueError(f"missing TTree {tree_name}")
            tree = root_file[tree_name]
            missing = set(branches) - set(tree.keys())
            if missing:
                raise ValueError(f"{tree_name} is missing branches: {', '.join(sorted(missing))}")
            return {name: tree[name].array(library="np") for name in branches}
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error


def read_sqc_pad_values(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return valid SQC pad positions and their corrected Vbd values."""
    arrays = read_tree_arrays(
        path, SQC_TREE, ("pad_position", VBD_BRANCH),
    )
    raw_positions = np.asarray(arrays["pad_position"])
    if not np.all(np.isfinite(raw_positions) & (raw_positions == np.floor(raw_positions))):
        raise ValueError(f"{path}: pad_position must contain finite integers")
    positions = np.asarray(raw_positions, dtype=np.int64)
    values = np.asarray(arrays[VBD_BRANCH], dtype=np.float64)
    if len(positions) != len(values) or not len(positions):
        raise ValueError(f"{path}: {SQC_TREE} has empty or inconsistent branches")
    if len(np.unique(positions)) != len(positions):
        raise ValueError(f"{path}: duplicate pad_position values in {SQC_TREE}")
    if np.any((positions < 1) | (positions > 225)):
        raise ValueError(f"{path}: pad_position must be between 1 and 225")

    valid = np.isfinite(values) & (values >= VALID_VBD_MIN_V) & (values <= VALID_VBD_MAX_V)
    return positions[valid], values[valid]


def read_sqc_columns(path: Path) -> dict[int, tuple[float, float, int]]:
    """Return channel -> (valid pad minimum, average, valid pad count)."""
    positions, values = read_sqc_pad_values(path)
    grouped: dict[int, tuple[float, float, int]] = {}
    for channel in range(1, N_CHANNELS + 1):
        channel_values = values[((positions - 1) % N_CHANNELS) == channel - 1]
        if len(channel_values):
            grouped[channel] = (
                float(np.min(channel_values)),
                float(np.mean(channel_values)),
                int(len(channel_values)),
            )
    return grouped


def read_cqc_channels(path: Path) -> dict[int, float]:
    """Return valid 20°C CQC Vbd values from this sensor file, indexed by channel."""
    arrays = read_tree_arrays(
        path, CQC_TREE,
        ("channel_id", VBD_BRANCH),
    )
    raw_ids = np.asarray(arrays["channel_id"])
    if not np.all(np.isfinite(raw_ids) & (raw_ids == np.floor(raw_ids))):
        raise ValueError(f"{path}: channel_id must contain finite integers")
    channel_ids = np.asarray(raw_ids, dtype=np.int64)
    values = np.asarray(arrays[VBD_BRANCH], dtype=np.float64)
    if len(channel_ids) != len(values):
        raise ValueError(f"{path}: inconsistent branch lengths in {CQC_TREE}")

    selected: dict[int, float] = {}
    seen: set[int] = set()
    for channel, value in zip(channel_ids, values):
        if not 1 <= channel <= N_CHANNELS:
            raise ValueError(f"{path}: invalid channel_id {channel} in {CQC_TREE}")
        if channel in seen:
            raise ValueError(f"{path}: duplicate channel_id {channel} in {CQC_TREE}")
        seen.add(int(channel))
        if math.isfinite(value) and VALID_VBD_MIN_V <= value <= VALID_VBD_MAX_V:
            selected[int(channel)] = float(value)
    return selected


def collect_residual_rows(sqc_files: list[Path], level: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[SensorKey] = set()
    for sqc_path in sqc_files:
        key = sqc_sensor_key(sqc_path)
        if key in seen:
            raise ValueError(f"multiple SQC ROOT files for sensor {key.label()}")
        seen.add(key)

        pad_positions, pad_values = read_sqc_pad_values(sqc_path)
        cqc_channels = read_cqc_channels(sqc_path)
        if not len(pad_values) or not cqc_channels:
            print(f"[skip] {key.label()}: no valid SQC pads or CQC channels in {sqc_path}")
            continue

        base_row = {
            "level": level,
            "sensor": key.label(),
            "batch": key.batch_group,
            "b_level": key.b_level,
            "wafer": key.wafer,
            "sensor_id": key.sensor,
            "sqc_root": str(sqc_path),
        }
        if level == "sensor-level":
            cqc_values = np.asarray(list(cqc_channels.values()), dtype=np.float64)
            sqc_min = float(np.min(pad_values))
            sqc_avg = float(np.mean(pad_values))
            cqc_min = float(np.min(cqc_values))
            cqc_avg = float(np.mean(cqc_values))
            rows.append({
                **base_row,
                "channel_id": "",
                "n_valid_sqc_pads": len(pad_values),
                "sqc_vbd_min_V": sqc_min,
                "sqc_vbd_avg_V": sqc_avg,
                "cqc_vbd_min_V": cqc_min,
                "cqc_vbd_avg_V": cqc_avg,
                "vbd_min_residual_V": sqc_min - cqc_min,
                "vbd_avg_residual_V": sqc_avg - cqc_avg,
            })
            continue

        sqc_channels = read_sqc_columns(sqc_path)
        for channel in range(1, N_CHANNELS + 1):
            sqc_values = sqc_channels.get(channel)
            cqc_vbd = cqc_channels.get(channel)
            if sqc_values is None or cqc_vbd is None:
                continue
            sqc_min, sqc_avg, n_pads = sqc_values
            rows.append({
                **base_row,
                "channel_id": channel,
                "n_valid_sqc_pads": n_pads,
                "sqc_vbd_min_V": sqc_min,
                "sqc_vbd_avg_V": sqc_avg,
                "cqc_vbd_min_V": cqc_vbd,
                "cqc_vbd_avg_V": cqc_vbd,
                "vbd_min_residual_V": sqc_min - cqc_vbd,
                "vbd_avg_residual_V": sqc_avg - cqc_vbd,
            })
    return rows


def gaussian(x: np.ndarray, amplitude: float, mu: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def common_histogram_edges(values: np.ndarray, bin_width: float) -> np.ndarray:
    low = math.floor(float(np.min(values)) / bin_width) * bin_width
    high = math.ceil(float(np.max(values)) / bin_width) * bin_width
    edges = np.arange(low, high + bin_width * 1.01, bin_width)
    if len(edges) < 4:
        center = 0.5 * (float(np.min(values)) + float(np.max(values)))
        edges = center + np.arange(-4, 5) * bin_width
    return edges


def fit_gaussian(values: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(values) < 3:
        raise ValueError(f"Gaussian fit requires at least 3 residuals; got {len(values)}")
    mu0 = float(np.mean(values))
    sigma0 = float(np.std(values, ddof=1))
    if not math.isfinite(sigma0) or sigma0 <= 0:
        raise ValueError("Gaussian fit requires residuals with non-zero spread")
    counts, edges = np.histogram(values, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    errors = np.sqrt(np.maximum(counts, 1))
    low = float(edges[0])
    high = float(edges[-1])
    initial = (float(max(counts)), mu0, max(sigma0, (high - low) / len(counts) / 2))
    parameters, covariance = curve_fit(
        gaussian, centers, counts, p0=initial, sigma=errors, absolute_sigma=True,
        bounds=([0.0, low, 1e-6], [np.inf, high, max(high - low, 1e-6)]),
        maxfev=20000,
    )
    parameter_errors = np.sqrt(np.diag(covariance))
    return parameters, parameter_errors


def save_residual_plot(values: np.ndarray, output: Path, title: str,
                       metric_label: str, level: str, bin_width: float) -> dict:
    edges = common_histogram_edges(values, bin_width)
    parameters, errors = fit_gaussian(values, edges)
    amplitude, mu, sigma = parameters
    mu_error, sigma_error = float(errors[1]), float(errors[2])
    hep.style.use("ATLAS")
    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    x_fit = np.linspace(edges[0], edges[-1], 500)
    ax.hist(values, bins=edges, histtype="stepfilled", linewidth=1.2,
            color="#2a78d6", edgecolor="#1c5cab", alpha=0.65,
            label="All batches")
    ax.plot(x_fit, gaussian(x_fit, amplitude, mu, sigma), color="#111111",
            linewidth=1.8, linestyle="--", label="Gaussian fit")
    ax.set_title(title)
    object_label = "Sensor" if level == "sensor-level" else "Channel"
    ax.set_xlabel(f"SQC VBD {metric_label} - CQC VBD [V]")
    ax.set_ylabel(f"{object_label.capitalize()}s / {bin_width:g} V")
    hep.atlas.label("HGTD Internal", data=True, rlabel="", loc=2, ax=ax)
    ax.text(0.97, 0.05,
            f"$\\mu$ = {mu:+.3f} $\\pm$ {mu_error:.3f} V\n"
            f"$\\sigma$ = {sigma:.3f} $\\pm$ {sigma_error:.3f} V\n"
            f"N = {len(values)}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=10,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 3})
    ax.legend(frameon=False, loc="upper right")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)
    return {
        "batch": "combined",
        "n_entries": len(values),
        "mu_V": float(mu),
        "mu_error_V": mu_error,
        "sigma_V": float(sigma),
        "sigma_error_V": sigma_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", nargs="+", type=Path, required=True,
                        help="sensor ROOT files, B-level directories, or batch-level directories")
    parser.add_argument("-l", "--level", required=True,
                        choices=("sensor-level", "channel-level"),
                        help="residual granularity: one value per sensor or per channel")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="output directory for two PDF histograms and CSV tables")
    parser.add_argument("--bin-width", type=float, default=0.5,
                        help="residual histogram bin width in volts (default: %(default)s)")
    args = parser.parse_args()
    if not math.isfinite(args.bin_width) or args.bin_width <= 0:
        parser.error("--bin-width must be a finite positive number")

    try:
        sqc_files = discover_root_files(args.input)
        if not sqc_files:
            raise ValueError("no sensor ROOT files found under the supplied input paths")
        rows = collect_residual_rows(sqc_files, args.level)
        if len(rows) < 3:
            raise ValueError(f"only {len(rows)} matched channel pairs; at least 3 are needed")

        output_dir = args.output.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics = (
            ("vbd_min_residual_V", "min", f"vbd_min_residual_{args.level}.pdf"),
            ("vbd_avg_residual_V", "avg", f"vbd_avg_residual_{args.level}.pdf"),
        )
        summary_rows = []
        level_title = "Sensor-level" if args.level == "sensor-level" else "Channel-level"
        for column, metric_label, filename in metrics:
            values = np.asarray([row[column] for row in rows], dtype=np.float64)
            fit = save_residual_plot(
                values, output_dir / filename, level_title, metric_label,
                args.level, args.bin_width,
            )
            summary_rows.append({"metric": column, **fit, "histogram": filename})

        residual_csv = output_dir / f"vbd_residuals_{args.level}.csv"
        with residual_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary_csv = output_dir / f"vbd_residual_fit_summary_{args.level}.csv"
        with summary_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]))
            writer.writeheader()
            writer.writerows(summary_rows)

        print(f"Matched sensors: {len({row['sensor'] for row in rows})}")
        print(f"Matched {args.level.removesuffix('-level')} entries: {len(rows)}")
        for summary in summary_rows:
            print(f"{summary['metric']} (all batches): "
                  f"mu={summary['mu_V']:+.3f} +/- {summary['mu_error_V']:.3f} V, "
                  f"sigma={summary['sigma_V']:.3f} +/- {summary['sigma_error_V']:.3f} V")
        print(f"Output: {output_dir}")
    except (FileNotFoundError, ImportError, OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
