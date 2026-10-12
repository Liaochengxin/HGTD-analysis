#!/usr/bin/env python3
"""Gaussian fit of per-pad SQC Vbd residuals against CQC channels.

SQC values come from ``pad_vbd.csv`` in each sensor input directory. The
extractor sums each pad's 15 pixel currents and finds the 7.5 uA crossing in
the 20 degC measurement without applying a temperature correction. CQC values come from each wafer's
``probe_card_channels.csv`` and are also corrected to 20 degC. SQC pad N is
paired with CQC channel N.

Missing SQC or CQC values remain blank in the detail CSV and are excluded
from the fit. Missing measurements are never replaced by zero.

Usage:
    python3 HGTD-analysis/SQC/fit_vbd_residual.py

    python3 HGTD-analysis/SQC/fit_vbd_residual.py \
        --sqc-dir SQC_results/CERN/2nd_batch \
        --sqc-pad-dir SQC_sample/2nd_batch_SQC \
        --cqc-dir CQC_results/CERN/2nd_batch_95_IHEP
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import mplhep
from mplhep.label import exp_text
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQC_DIR = REPOSITORY_ROOT / "SQC_results/CERN/2nd_batch"
DEFAULT_SQC_PAD_DIR = REPOSITORY_ROOT / "SQC_sample/2nd_batch_SQC"
DEFAULT_CQC_DIR = REPOSITORY_ROOT / "CQC_results/CERN/2nd_batch_95_IHEP"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "vbd_residual_fits"

RESULT_GROUP_RE = re.compile(r"B(?P<batch>\d+)")
RESULT_SENSOR_RE = re.compile(r"W(?P<wafer>\d+)-P(?P<pos>\d+)")

N_PADS = 15
DEFAULT_BIN_WIDTH = 0.5

# Series blue for the histogram, near-black for fit elements (ATLAS style base).
SERIES = "#2a78d6"
SERIES_DARK = "#1c5cab"
INK = "#0b0b0b"


def read_cqc_channels(path: Path, sensor_location: int) -> dict[int, dict]:
    """Return CQC channel rows for one sensor location, indexed by channel."""
    channels = {}
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"sensor_location", "channel", "sensor_class", "vbd_20C_V",
                    "leakage_current_A"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain columns: {', '.join(sorted(required))}")
        for row in reader:
            if (row.get("sensor_location") or "").strip() != str(sensor_location):
                continue
            channel = int(row["channel"])
            if channel in channels:
                raise ValueError(f"duplicate sensor/channel row: {sensor_location}/{channel} in {path}")
            vbd_text = (row.get("vbd_20C_V") or "").strip()
            leakage_text = (row.get("leakage_current_A") or "").strip()
            channels[channel] = {
                "sensor_class": (row.get("sensor_class") or "").strip(),
                "cqc_channel_vbd": float(vbd_text) if vbd_text else None,
                "leakage_current_A": float(leakage_text) if leakage_text else None,
            }
    return channels


def read_sqc_pads(path: Path, sensor_location: int) -> dict[int, dict]:
    """Return extracted SQC pad rows indexed by pad number."""
    pads = {}
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"sensor_location", "pad", "vbd_20C_V", "n_pixels"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain columns: {', '.join(sorted(required))}")
        for row in reader:
            if (row.get("sensor_location") or "").strip() != str(sensor_location):
                continue
            pad = int(row["pad"])
            if pad in pads:
                raise ValueError(f"duplicate sensor/pad row: {sensor_location}/{pad} in {path}")
            value = (row.get("vbd_20C_V") or "").strip()
            pads[pad] = {
                "sqc_pad_vbd": float(value) if value else None,
                "n_pixels": int(row["n_pixels"] or 0),
            }
    return pads


def collect_pad_residuals(sqc_dir: Path, sqc_pad_dir: Path,
                          cqc_dir: Path) -> list[dict]:
    """Pair each extracted SQC pad Vbd with its corresponding CQC channel."""
    rows = []
    for crosscheck in sorted(sqc_dir.glob("B*/W*-P*/crosscheck.csv")):
        group_match = RESULT_GROUP_RE.fullmatch(crosscheck.parent.parent.name)
        sensor_match = RESULT_SENSOR_RE.fullmatch(crosscheck.parent.name)
        if group_match is None or sensor_match is None:
            print(f"  [skip] {crosscheck.parent}: expected B<batch>/W<wafer>-P<location>")
            continue
        batch = int(group_match.group("batch"))
        wafer = int(sensor_match.group("wafer"))
        pos = int(sensor_match.group("pos"))
        label = f"B{batch:02d}/W{wafer:02d}-P{pos}"
        sensor_dir = sqc_pad_dir / f"B{batch}" / f"W{wafer}_P{pos}"
        sqc_csv = sensor_dir / "pad_vbd.csv"
        cqc_csv = cqc_dir / f"B{batch}_{wafer}" / "probe_card_channels.csv"
        sqc_pads = {}
        if sqc_csv.is_file():
            try:
                sqc_pads = read_sqc_pads(sqc_csv, pos)
            except (OSError, ValueError) as error:
                print(f"  [warn] {label}: cannot read SQC pad data: {error}")
        else:
            print(f"  [warn] {label}: missing SQC pad file {sqc_csv}")
        cqc_channels = {}
        if cqc_csv.is_file():
            try:
                cqc_channels = read_cqc_channels(cqc_csv, pos)
            except (OSError, ValueError) as error:
                print(f"  [warn] {label}: cannot read CQC channel data: {error}")
        else:
            print(f"  [warn] {label}: missing CQC channel file {cqc_csv}")
        for pad in range(1, N_PADS + 1):
            sqc = sqc_pads.get(pad, {})
            channel = cqc_channels.get(pad, {})
            cqc_vbd = channel.get("cqc_channel_vbd")
            sqc_vbd = sqc.get("sqc_pad_vbd")
            rows.append({
                "label": label,
                "sensor_location": pos,
                "pad": pad,
                "channel": pad,
                "n_pixels": sqc.get("n_pixels", 0),
                "sqc_pad_vbd": sqc_vbd,
                "sensor_class": channel.get("sensor_class", ""),
                "cqc_channel_vbd": cqc_vbd,
                "leakage_current_A": channel.get("leakage_current_A"),
                "residual": sqc_vbd - cqc_vbd
                if sqc_vbd is not None and cqc_vbd is not None else None,
            })
    return rows


def gaussian(x, amp, mu, sigma):
    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def fit_gaussian(residuals: np.ndarray, nsigma: float, bin_width: float = 0.5):
    """Trimmed Gaussian fit (unbinned MLE) with a robust rejection window.

    Rejection uses median(residuals) +/- nsigma x MAD-spread: the median/MAD
    have a 50% breakdown point, so catastrophic outliers (e.g. a dead sensor
    hundreds of volts off) cannot bias the window.  mu and sigma then come
    from the closed-form unbinned MLE of the kept sample.  A binned
    least-squares fit is deliberately avoided: with few events most bins are
    empty and its chi2 is biased towards narrow sigma, with results that
    depend strongly on the bin width.  The histogram is for display only.
    """
    mu0 = float(np.median(residuals))
    sigma0 = max(1.4826 * float(np.median(np.abs(residuals - mu0))), bin_width)
    keep = np.abs(residuals - mu0) <= nsigma * sigma0
    values = residuals[keep]
    n = len(values)
    if n < 3:
        return mu0, sigma0, 0.0, 0.0, keep, False, (np.array([]), np.array([])), 0.0

    mu = float(values.mean())
    sigma = float(values.std())
    mu_err = sigma / math.sqrt(n)
    sigma_err = sigma / math.sqrt(2 * n)

    counts, edges = np.histogram(values, bins=np.arange(mu0 - nsigma * sigma0,
                                                        mu0 + nsigma * sigma0 + bin_width / 2,
                                                        bin_width))
    amp = n * bin_width / (sigma * math.sqrt(2 * math.pi))
    return mu, sigma, mu_err, sigma_err, keep, True, (counts, edges), amp


def draw_series(ax, values: np.ndarray, fit: tuple, bin_width: float,
                xlabel: str, ylabel: str) -> None:
    """One residual histogram with its Gaussian overlay (ATLAS style)."""
    mu, sigma, mu_err, sigma_err, keep, converged, hist, amp = fit
    counts, edges = hist
    if not converged or counts.size == 0:
        raise SystemExit(f"fit did not converge (N={len(values)} after trimming)")
    plt.sca(ax)
    centers = 0.5 * (edges[:-1] + edges[1:])
    ax.hist(centers, bins=edges, weights=counts, histtype="stepfilled",
            color=SERIES, alpha=0.85, edgecolor=SERIES_DARK,
            linewidth=1.0, label="residuals")

    x_fit = np.linspace(edges[0], edges[-1], 500)
    ax.plot(x_fit, gaussian(x_fit, amp, mu, sigma), color=INK,
            linewidth=1.8, label="Gaussian fit")

    ax.axvline(mu, color=INK, linewidth=1, linestyle="--")

    exp_text(exp="HGTD", text="Internal", loc=0)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.text(
        0.96, 0.95,
        f"$\\mu$ = {mu:+.2f} $\\pm$ {mu_err:.2f} V\n"
        f"$\\sigma$ = {sigma:.2f} $\\pm$ {sigma_err:.2f} V\n"
        f"N = {len(values)}",
        transform=ax.transAxes, ha="right", va="top", fontsize=12,
    )
    ax.legend(frameon=False, fontsize=11, loc="upper left")


def print_fit_report(values: np.ndarray, fit: tuple,
                     rows: list[dict], nsigma: float) -> None:
    mu, sigma, mu_err, sigma_err, keep, converged, _, _ = fit
    print(f"\nMatched pad/channel residuals: {len(values)}")
    print(f"Gaussian fit        : mu = {mu:+.3f} +/- {mu_err:.3f} V, "
          f"sigma = {sigma:.3f} +/- {sigma_err:.3f} V  (converged={converged})")
    print(f"Outliers (> {nsigma} sigma, excluded): {int((~keep).sum())}")
    for r, ok in zip(rows, keep):
        if not ok:
            print(f"  {r['label']:<20s} pad {r['pad']:>2d}  "
                  f"res={r['residual']:+7.2f}  <-- outlier")


def run_pad_mode(args: argparse.Namespace) -> None:
    rows = collect_pad_residuals(args.sqc_dir, args.sqc_pad_dir, args.cqc_dir)
    fit_rows = [row for row in rows if row["residual"] is not None]
    if len(fit_rows) < 3:
        raise SystemExit(f"only {len(fit_rows)} valid pad/channel pairs; at least 3 are required")
    values = np.array([row["residual"] for row in fit_rows])
    print(f"\nMatched SQC pad/channel rows: {len(rows)}")
    print(f"Missing SQC/CQC Vbd pairs (excluded): "
          f"{sum(row['residual'] is None for row in rows)}")
    bin_width = args.bin_width or DEFAULT_BIN_WIDTH
    fit = fit_gaussian(values, args.nsigma, bin_width)
    print_fit_report(values, fit, fit_rows, args.nsigma)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use(mplhep.style.ATLAS)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=200)
    draw_series(ax, values, fit, bin_width,
                "SQC pad Vbd $-$ CQC channel Vbd  [V]",
                f"Pads / {bin_width:g} V")
    fig.tight_layout()
    plot_path = args.output_dir / "vbd_residual_fit_pad.png"
    fig.savefig(plot_path, facecolor="white", bbox_inches="tight")

    csv_path = args.output_dir / "vbd_residuals_pad.csv"
    used = {id(row): bool(ok) for row, ok in zip(fit_rows, fit[4])}
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "label", "sensor_location", "sensor_class", "pad", "channel", "n_pixels",
            "sqc_pad_vbd", "cqc_channel_vbd", "leakage_current_A",
            "residual", "used_in_fit"])
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "used_in_fit": used.get(id(r), False)})
    print(f"figure -> {plot_path}")
    print(f"residuals -> {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sqc-dir", type=Path, default=DEFAULT_SQC_DIR,
                        help="SQC output: <sqc-dir>/B<batch>/W<wafer>-P<location>/crosscheck.csv")
    parser.add_argument("--sqc-pad-dir", type=Path, default=DEFAULT_SQC_PAD_DIR,
                        help="SQC input/output root: <root>/<batch>/W<wafer>_P<pos>/pad_vbd.csv")
    parser.add_argument("--cqc-dir", type=Path, default=DEFAULT_CQC_DIR,
                        help="CQC output: <cqc-dir>/B<batch>_<wafer>/probe_card_channels.csv")
    parser.add_argument("--nsigma", type=float, default=3.0,
                        help="outlier rejection threshold in sigmas")
    parser.add_argument("--bin-width", type=float, default=None,
                        help="histogram bin width in V (default: 0.5 V)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    run_pad_mode(args)


if __name__ == "__main__":
    main()
