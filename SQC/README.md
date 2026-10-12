# SQC sensor cross-check workflow

> 中文版: [README_CN.md](README_CN.md)

This workflow compares needle-station SQC data (225 pads per sensor) with
15-channel probe-card CQC data using `temp_vbdmin_cross_toIME_v2.C`. A shared
sensor plan drives both local execution and cluster submissions.

## Workflow

1. Put needle and probe-card data in the expected directory layouts.
2. Set paths, temperatures, and run mode in `config.yaml`.
3. Preview the sensor-to-CQC matches with `--dry-run`.
4. Run sequentially on a workstation or submit one job per sensor to IHEP or
   CERN.
5. After cluster jobs finish, collect each sensor's `crosscheck.csv` into one
   `summary_all.csv`.

## Input layout

Set `sqc_folder` to the batch directory for this run. The workflow discovers
`B*/W*_P*/SweepVoltage0` directly under that directory and does not scan other
batches under the common parent. To switch batches, change `sqc_folder` in
`config.yaml`:

```text
SQC_sample/
├── 1st_batch_SQC/
│   └── B31/W22_P3/SweepVoltage0/...
└── 2nd_batch_SQC/
    └── B33/
        └── W9_P4/
            └── SweepVoltage0/
                ├── 1-1.csv
                ├── 1-2.csv
                └── ... 1-225.csv
```

The CQC folder must contain extracted per-wafer data and a temperature table:

```text
CQC_sample/CERN/2nd_batch_95/               # cqc_folder
├── wafer_temperature_template.csv
└── B31_15/
    └── 20WS0013100015/
        ├── 20WS2031001501-1.csv
        ├── ...
        └── 20WS2031001501-15.csv
```

Each CQC wafer has 52 sensors × 15 channel CSVs. `cqc_fallback_folder` may
point to an older extracted CQC tree. Matching priority is: exact wafer/sensor
match in `cqc_folder`, exact sensor match in the fallback tree, then a
placeholder from available CQC data. The plan prints the source for every
sensor. Review it before running: a placeholder is useful for exercising the
macro, but its ProbeCard result is not a real cross-check. If no CQC file is
available at all, that sensor is skipped. If the temperature table has no
entry for a wafer, the plan warns and uses `Tp=20°C`.

## Environment and configuration

Python 3 and PyYAML are needed to build the plan and generate jobs. From the
repository root, create the virtual environment and install the requirements:

```bash
python3 -m venv HGTD-analysis/.venv
source HGTD-analysis/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r HGTD-analysis/requirements.txt
```

Local runs use the workstation's existing ROOT installation and do not load
ATLAS environment setup. Cluster jobs source ATLAS setup and load the same ROOT
release as CQC:

```bash
export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase
source "$ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh"
lsetup 'root 6.40.02-x86_64-el9-gcc15-opt'
```

`config.yaml` stores `main_path` as an absolute path; all other data, macro,
job, and output paths are relative to it. Key settings:

| Key | Purpose |
|---|---|
| `mode` | Cluster submission target: `ihep` or `cern`; local execution uses `run_all_sqc.py` directly |
| `sqc_folder` | Selected needle-station batch directory, for example `SQC_sample/2nd_batch_SQC` |
| `cqc_folder` | Primary extracted CQC batch, including its temperature table |
| `cqc_fallback_folder` | Optional older CQC data for exact or placeholder matching |
| `temp_file` | CQC wafer temperature table |
| `tn` | Needle-station temperature in °C; currently assumed to be 20°C |
| `root_version` | ROOT release loaded on cluster workers; aligned with CQC |
| `output_path` | Shared result directory for local and cluster jobs |
| `job_folder` | Generated submission package directory; its final directory name is the default CERN HTCondor batch name |

For the current CQC layout, the primary path is
`CQC_sample/CERN/2nd_batch_95`; update `cqc_folder` and `temp_file` together
when changing batches. The tracked config currently targets CERN HTCondor
(`mode: cern`) and uses `flavour: microcentury` with the shared-filesystem
`main_path`. For local runs, set
`main_path` to the local repository root; `run_all_sqc.py` does not require a
cluster mode setting.

## Preview or run locally

Preview the plan without running ROOT:

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py \
  HGTD-analysis/SQC/config.yaml --dry-run
```

The tracked config currently points to the second batch. To process the first
batch, change `sqc_folder` to `SQC_sample/1st_batch_SQC`. No batch or sensor
filter arguments are used at run time.

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py \
  HGTD-analysis/SQC/config.yaml --dry-run
```

Results are grouped by sensor batch number. Each sensor directory contains
`crosscheck.csv`, `run.log`, plots, and one ROOT file named after the sensor;
the plan and combined summary remain at the `output_path` root:

```text
results/
├── B15/
│   └── W11-P2/
├── B18/
│   └── W01-P7/
├── sensor_plan.csv
└── summary_all.csv
```

`sensor_plan.csv` records the chosen CQC source and temperature;
`summary_all.csv` collects the available sensor summaries across the `Bxx`
directories.

## Submit to IHEP

Run the generator on the IHEP machine after all input data are in their final
shared-filesystem locations. Set `mode: ihep`, `main_path`, and `sqc_folder`
to the selected batch directory in the config before generating the package:

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py \
  HGTD-analysis/SQC/config.yaml
cd HGTD-analysis/SQC/jobs
./submit_all.sh
```

The package contains `sensors.list`, `job.sh`, `submit_all.sh`, and
`collect_results.py`. One `hep_sub` call creates one ProcId per sensor. Each
job initializes ATLAS/ROOT, runs one sensor, and writes directly to the shared
`output_path`. Check jobs with `hep_q -u`; per-job scheduler logs are under
`job_folder/logs/`. After all jobs finish, collect the results:

```bash
python3 collect_results.py
```

## Submit to CERN EosSubmit

Place SQC data, CQC data, the repository, and output on paths accessible to
the CERN workers (normally EOS). Set `mode: cern` and configure `main_path`,
the selected batch-level `sqc_folder`, `cqc_folder`, `temp_file`, and
`output_path` before generating the package:

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py \
  HGTD-analysis/SQC/config.yaml
cd HGTD-analysis/SQC/jobs
./submit_all.sh
```

The generator creates `sensors.list`, `job.sh`, `cern_batch.sub`,
`source.tar`, and `collect_results.py`. `source.tar` freezes the ROOT macro;
the worker reads data and writes results by their configured EOS paths. Each
sensor is one Condor job. By default, the final directory name in `job_folder`
is used as the HTCondor batch name, shown by `condor_q -batch`. Pass optional
`--jobs NAME` to override it. After completion, run
`python3 collect_results.py` from the generated job directory.

## Calculation and interpretation

The macro finds Vbd by linear interpolation at 7.5 µA for each probe-card
channel and 0.5 µA for each needle pad. It corrects both to 20°C using
`Vbd(20°C) = Vbd − (T−20) × 1.1 V/°C`. It then evaluates leakage current at
`0.8 × VbdMin` for each measurement side and produces Vbd/leakage maps,
histograms, overlaid I-V curves, and `crosscheck.csv`.

`crosscheck.csv` has four groups: `ProbeCard`, `Needle`, `Needle(inner)`, and
`Needle(inner2)`. `Valid` is a count in the 165–195 V acceptance interval
(15 channels for ProbeCard, 225 pads for Needle); it is not a good-pad
fraction. The configured needle temperature `tn: 20.0` is an assumption and
should be updated if the measured station temperature is known.

Each sensor ROOT file contains two TTrees. `SQC_results` has one entry per SQC
pad (225 entries): `pad_position` (matching the `1-<position>.csv` input),
`vbd_corrected_20C_V`, and `leakage_current_A`. `CQC_results` stores the
15 matched CQC channel results, one entry per channel, with `channel_id`,
`vbd_corrected_20C_V`, and `leakage_current_A`. These values come from the CQC
channel curves already read for that SQC calculation; Vbd is corrected to
20°C, and leakage current is interpolated at `0.8 × ProbeCard VbdMin`. SQC pad
leakage current in `SQC_results` is interpolated at `0.8 × Needle VbdMin`.
Maps, distributions, and I-V plots are exported as PDF files beside the ROOT
file.

`process_perpad.C`, `run.C`, and `PlotSensorVbd_multibatches.C` are separate
legacy plotting/summing tools; they are not part of the batch workflow above.

## Plot SQC sensor and pad Vbd distributions

Use the single entry point `plot_vbd.py`; `--level` selects the input and
plotting path. For `sensor-level`, pass an SQC batch results directory. The
script recursively reads each sensor's `crosscheck.csv`, selects only the
`Group=Needle(inner)` row, and creates separate Vbd average (`Mean`), minimum
(`VbdMin`), and RMS PDFs. The default output is
`<input directory>/vbd_sensor_plots/`; pass `--output` to choose another
output directory:

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/SQC/plot_vbd.py \
  SQC_results/CERN/1nd_batch \
  --level sensor-level \
  --output HGTD-analysis/SQC/plots/1nd_batch_sensor_vbd
```

For `pad-level`, pass one sensor ROOT file. The script reads each pad's
corrected-to-20°C `vbd_corrected_20C_V` from the `SQC_results` TTree and creates
one histogram. By default, the PDF is written beside the ROOT file; `--output`
takes a PDF file path:

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/SQC/plot_vbd.py \
  HGTD-analysis/SQC/results/B06/W01-P2/W01-P2.root \
  --level pad-level \
  --output HGTD-analysis/SQC/plots/W01-P2_pad_vbd.pdf
```

Both modes use mplhep's ATLAS style, label the plots `HGTD Internal`, and omit
the collision-energy label. ROOT files are read with `uproot`, included in
`HGTD-analysis/requirements.txt`.

## Summarize stored results

From `/eos/user/l/liaoc/public/HGTD_sensor`, run:

```bash
python3 HGTD-analysis/SQC/collect_results.py SQC_results/CERN/1nd_batch
python3 HGTD-analysis/SQC/collect_results.py SQC_results/CERN \
  --output SQC_results/CERN/summary_all.csv
```

The collector uses each batch's `sensor_plan.csv`, preserves `Tp` and `Tn`,
and adds `batch`, `output_group`, and `output_sensor` identity columns.
It reports planned sensors without a crosscheck and fails on unplanned or
duplicate identities. Generated job collectors use this same implementation
and retain their configured CERN output root; their optional positional input
can select results moved into the current `SQC_results/CERN` tree.
See [the current results audit](../doc/POST_PROCESSING_AUDIT_CN.md).
