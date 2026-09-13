# HGTD Sensor SQC Analysis

> 中文版: [README_CN.md](README_CN.md)

This directory performs SQC cross-checks on HGTD LGAD sensors: for each
sensor (a 15×15 = 225-pad array), the needle-station (per-pad) I-V data is
compared against the 15×1 probe-card (per-column) I-V data, using the ROOT
macro `temp_vbdmin_cross_toIME_v2.C`.

Macro processing chain:

1. Vbd is defined as the point where the I-V curve crosses 0.5 µA/pad
   (needle) or 7.5 µA/column (probe card, = 15 × 0.5 µA), obtained by linear
   interpolation, with temperature correction
   `Vbd(20°C) = Vbd − (T−20) × 1.1 V/°C`;
2. The leakage current of every pad/channel is interpolated at a common bias
   of `0.8 × VbdMin`;
3. Outputs: Vbd map, leakage map, histograms, overlaid I-V curves, and the
   statistics table `crosscheck.csv` (pass criterion: 165 V ≤ Vbd(20°C) ≤ 195 V,
   counted as `Valid`).

## 1. Data layout

```text
SQC_sample/                        # Needle (SQC) data, two test campaigns
├── 1st_batch_SQC/B<batch>/W<wafer>_P<pos>/SweepVoltage0/1-<pad>.csv   (×225)
└── 2n_batch_SQC/B<batch>/W<wafer>_P<pos>/SweepVoltage0/1-<pad>.csv   (×225)

CQC_sample/2nd_batch_95/           # Probe-card (CQC) data (extracted by script/unzip_cqc.py)
└── B<batch>_<wafer>/<wafer serial>/20WS20<batch><wafer><pos>-<channel>.csv   (780 per wafer)

test_CQC/                          # Two wafers extracted manually, kept as a fallback source
CQC_sample/2nd_batch_95/wafer_temperature_template.csv   # CQC test temperature per wafer
```

Temperature-table serial rule: `20WS0013 + <last digit of batch> + {wafer:05d}`,
e.g. `20WS0013100015` for batch B31, wafer 15.

## 2. config.yaml

All global parameters live in this single config. `main_path` is absolute;
every other entry is a path relative to it:

```yaml
main_path: /lustrefs/atlas/SUSY/users/liaocx/HGTD/
sqc_folder: SQC_sample                                      # needle data root
cqc_folder: CQC_sample/2nd_batch_95                         # real CQC match source
cqc_fallback_folder: test_CQC                               # legacy CQC fallback
temp_file: CQC_sample/2nd_batch_95/wafer_temperature_template.csv
macro: HGTD-analysis/SQC/temp_vbdmin_cross_toIME_v2.C
output_path: HGTD-analysis/SQC/results
tn: 20.0                                                    # needle test temperature (°C)
```

Probe-card matching priority (`find_cqc`):

1. Real match in `cqc_folder` by directory name `B<batch>_<wafer>`; Tp is
   taken from the temperature table via the exact wafer serial;
2. Exact serial match `20WS2<batch><wafer><pos>` in `cqc_fallback_folder`;
3. If neither hits, any real probe-card data set is used as a placeholder —
   the placeholder only affects the ProbeCard side of the output; the needle
   (SQC) results do not depend on it.

Currently all 2nd-campaign sensors (B31/B33/B36) match for real; 1st-campaign
sensors (B06/B07/B15/B18/B21) have no CQC counterpart yet and use placeholders.

## 3. Local batch run

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml --filter B31
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml --dry-run
```

The script scans all `B*/W*_P*/SweepVoltage0` under `sqc_folder` and runs the
macro once per sensor (~2 s each). Output goes to
`output_path/<campaign>-B<batch>-W<wafer>-P<pos>/`, aggregated into
`output_path/summary_all.csv` (4 rows per sensor: ProbeCard / Needle / inner /
inner2 with Mean, RMS, VbdMin, IRatio, LKG, Valid).

## 4. IHEP cluster submission

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py HGTD-analysis/SQC/config.yaml
cd condor && ./submit_all.sh
```

`make_condor_jobs.py` scans all sensors and generates the `condor/` package:

```text
condor/
├── sensors.list        # one sensor per line: label|Tp|probe-card path|needle path
├── job.sh              # $1 = ProcId → sensors.list line → root macro
├── submit_all.sh       # a single hep_sub job.sh -argu "%{ProcId}" -n N
├── root_env.sh         # cluster ROOT setup (edit if needed)
└── collect_results.py  # merges results/*/crosscheck.csv → summary_all.csv when done
```

A single `hep_sub` call creates one job cluster (same cluster id):
N sensors = N ProcIds, one sensor per job, running in parallel.

Note: the generated job files contain **absolute paths** (config `main_path`
+ relative paths), so `make_condor_jobs.py` must be run once **on the
cluster**, at the final location, after the data is in place. Exclude zip
files when uploading: `tar czvf target.tar.gz --exclude='*.zip' ...`.

Job management:

```bash
hep_q -u $USER        # check status
hep_rm <clusterid>    # remove the whole cluster
```

## 5. Known caveats

- **Tn = 20 is an assumption.** Measured sensors consistently show a
  ~9–13 V systematic offset (probe card lower than needle, e.g. B31-W15:
  182 vs 194), which pushes Vbd out of the 165–195 V acceptance window and
  distorts `Valid` (e.g. 0/225 and 1/225 on the two B36 sensors, although
  there is no large-scale damage). Once the real needle-station temperature
  is confirmed, update `tn` in the config and rerun;
- `Valid` is the fraction falling inside the 165–195 V window, not the
  fraction of good pads — beware of systematic offsets when interpreting it;
- Three needle directories contain 226 files (one extra); the macro only
  reads 1–225, so this is harmless;
- `process_perpad.C` / `run.C` are early single-column summing tools, not yet
  config-driven; run directly with `root -l -b -q run.C`.
