# CQC sensor IV workflow

> 中文说明见 [README_CN.md](README_CN.md).

This workflow runs `Card52_v3.C` on extracted wafer IV curves, collects sensor
grades, compares IHEP and IME yields, and packages the outputs for transfer.

## Workflow at a glance

1. Prepare the sample tree and extract each raw ZIP once.
2. Run one of the three modes: local, IHEP cluster, or CERN cluster.
3. Wait for all wafer jobs to finish and confirm each wafer has
   `sensorYield(s).csv` in the results tree.
4. Run `collect_sensor_yields.py` for IHEP and IME, then run
   `summarize_sensor_yields.py` to make the grade-count cross-check.
5. Zip the completed results tree and transfer the archive.

## Inputs and environment

Set `wafer_folder` to a batch directory. It contains one directory per wafer
and the temperature table used by the ROOT analysis. For example:

```text
CQC_sample/
└── IHEP/
    └── 1nd_batch_25/                         # wafer_folder
        ├── wafer_temperature_template.csv     # required for analysis
        ├── B34_10/
        │   ├── 20WS0013400010.zip             # original archive
        │   ├── 20WS0013400010/                 # extracted input; required
        │   │   ├── 20WS20340010-1.csv
        │   │   ├── 20WS20340010-2.csv
        │   │   └── ...                         # 780 IV CSVs total
        │   ├── sensor_attributes_template_20WS0013400010.CSV
        │   ├── sensor_parts_template_20WS0013400010.CSV
        │   ├── parttree_sensor_20WS0013400010.CSV
        │   └── sensorYields.csv                # existing IME/vendor yields;
        │                                       # used for cross-check only
        ├── B34_11/
        │   └── ...                             # same layout per wafer
        └── ...
```

The batch root must contain `wafer_temperature_template.csv`. Each wafer must
have one extracted subdirectory named after its `20WS...` serial; the config
generator skips wafer directories without one. Its contents are the per-column
IV CSVs (52 sensors × 15 columns = 780 files). The root analysis needs these
CSVs and the temperature table. The metadata CSVs are retained with the sample
for sensor/wafer bookkeeping, while `sensorYields.csv` is the existing
IME/vendor result used by the optional yield cross-check. The original ZIPs
are retained; extraction is performed by:

```bash
python3 HGTD-analysis/scirpt/unzip_cqc.py \
  CQC_sample/IHEP/1nd_batch_25
```

Pass the batch directory as the positional argument; the helper searches it
recursively, extracts ZIPs beside their wafer directories, and skips archives
that are already extracted. Change the argument to the batch being processed,
for example `CQC_sample/CERN/2nd_batch_95`. For a new batch, preserve the same
batch-root / wafer-directory / serial-subdirectory structure. When transferring
the sample to IHEP, the original ZIPs can be excluded if the extracted
directories are included.

Create and activate a Python virtual environment from the repository root,
then install the dependencies from the requirements file:

```bash
python3 -m venv HGTD-analysis/.venv
source HGTD-analysis/.venv/bin/activate
python -m pip install --upgrade pip
python3 -m pip install -r HGTD-analysis/requirements.txt
```

Run the workflow commands in that activated environment. When finished, leave
it with `deactivate`. ROOT is a system dependency and is not installed by
`requirements.txt`; make sure `root` is available on `PATH` (the CERN jobs use
ROOT 6.40).

## Choose a run mode

| Mode | Where it runs | How jobs are submitted | Result location |
|---|---|---|---|
| Local | Your workstation | `run_all.sh` runs wafer configs sequentially | `HGTD-analysis/CQC/results/<wafer>/` |
| IHEP cluster | IHEP shared filesystem | One `hep_sub` cluster, one ProcId per wafer | `HGTD-analysis/CQC/results/<wafer>/` on the shared filesystem |
| CERN cluster | CERN HTCondor EosSubmit | `condor_submit`, one job per wafer; inputs and outputs are read/written directly on EOS | `eos_output_dir/<wafer>/` from the selected CERN config |

Use the matching generator configuration as the starting point:

| Config | Mode and sample |
|---|---|
| `config_generator_local.yaml` | Local; currently points to IHEP `1nd_batch_25` |
| `config_generator.yaml` | IHEP cluster; currently points to IHEP `1nd_batch_25` |
| `config_generator_cern.yaml` | CERN cluster; CERN `2nd_batch_95` |

For a different batch, update `wafer_folder` and `temp_file` together. For
local and IHEP configs, also check `main_path`, the absolute path to the
repository on the machine that will run the generator and jobs. Output,
config, script, and log paths are relative to `main_path`. For CERN mode,
`eos_input_dir`, `eos_output_dir`, and `venv_path` are absolute EOS paths
embedded in the generated job wrapper; update them for your CERN EOS area.

Generate the configs and submit files from the repository root. Replace the
config filename with the chosen mode and batch:

```bash
python3 HGTD-analysis/CQC/generate_configs.py \
  HGTD-analysis/CQC/config_generator_local.yaml
```

The generator scans wafer folders that contain an extracted `20WS...`
directory. Extract the sample data before generating configs.

## Run locally

After generating local configs, run all wafers sequentially:

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

To run just one wafer, pass its generated config directly:

```bash
python3 HGTD-analysis/CQC/run_local.py \
  HGTD-analysis/CQC/configs/config_B34_2.yaml
```

## Submit on the IHEP cluster

Transfer the repository/sample tree to a path shared with IHEP worker nodes.
For a macOS-created tarball, omit extended attributes and the original ZIPs
(the extracted CSVs are what the jobs read):

```bash
tar czf HGTD_sensor.tar.gz --no-xattrs --no-mac-metadata \
  --exclude='*.zip' -C /path/to/parent HGTD_sensor
```

On the IHEP machine, unpack the tree, set `main_path` in
`config_generator.yaml` to its shared path, and set `wafer_folder` and
`temp_file` to the selected batch. Generate the submit script there, then
submit it:

```bash
python3 HGTD-analysis/CQC/generate_configs.py \
  HGTD-analysis/CQC/config_generator.yaml
bash HGTD-analysis/CQC/jobs/run_all.sh
```

IHEP mode creates one `hep_sub` cluster with one process per discovered wafer.
The generated script maps each process ID to the corresponding wafer config.
Check the queue with `hep_q -u`; stdout and stderr are written under the
configured `log_folder` as `job_<ProcId>.out` and `job_<ProcId>.err`.

## Submit on the CERN cluster

CERN mode uses EOS paths for both input and output. The login-side generator
uses the tracked `config_generator_cern.yaml` to create `filelist.txt`,
`job.sh`, `cern_batch.sub`, and a frozen `src.tar` containing the analysis
macro and runner. Transfer these generated submit files to the EOS submit
directory configured for your campaign, with `out/` and `logs/` directories
present, then submit from that directory:

```bash
cd /eos/user/<user>/HGTD/CQC_batch
condor_submit cern_batch.sub
```

Each queued wafer runs as a separate job. The job reads extracted CSVs and
temperature data from `eos_input_dir` and writes results directly to
`eos_output_dir/<wafer>/`. Check the Condor queue and per-job `.out`/`.err`
files in the submit directory. Regenerate and transfer `src.tar` whenever
`Card52_v3.C` or `run_local.py` changes; running jobs use the snapshot they
received at submission.

## Results

Each successful wafer job creates a directory like:

```text
results/<batch>/<wafer>/
├── sensorYield.csv
├── VbdMap.png
├── LKGnoMap.png
├── IV_Full.png
├── Sensor_Grade_Map.png
├── run.log
└── sensor_1/ ... sensor_52/
```

The output summary is named `sensorYield.csv` by current runs; the collector
also accepts historical `sensorYields.csv` and serial-number CSV filenames.
Review job logs and ensure the expected per-wafer summary CSVs exist before
starting post-processing. CERN mode's `<batch>` directory is the configured
EOS output directory; local and IHEP modes can use a batch-specific output
directory by setting `output_path` in their generator config accordingly.

## Post-process IHEP and IME yields

The collector adds wafer serial/name columns and groups rows into `A.csv`,
`B.csv`, and `C.csv`. A sensor whose final status is neither A nor C goes into
the B table. `summarize_sensor_yields.py` then counts these grades per wafer
for each test and writes side-by-side tables. The resulting IHEP/IME count
difference is the yield cross-check.

The scripts currently resolve relative paths from
`/eos/user/l/liaoc/public/HGTD_sensor` (see `MAIN_PATH` in each script).
Run them on that EOS tree, or change `MAIN_PATH` to the repository root on the
machine doing post-processing. The examples below assume that root and a
results layout under `HGTD-analysis/CQC/results/<batch>/`.

First collect IHEP analysis results. `--sample` points to the matching sample
tree for the wafer serial mapping; `--output` keeps the collected tables in
the results directory:

```bash
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  HGTD-analysis/CQC/results/1nd_batch_25 \
  --sample CQC_sample/IHEP/1nd_batch_25 \
  --output HGTD-analysis/CQC/results/1nd_batch_25
```

Collect the IME/vendor yields from their wafer directories. Give the output a
label so it does not overwrite the IHEP grade tables:

```bash
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  CQC_sample/IHEP/1nd_batch_25 \
  --sample CQC_sample/IHEP/1nd_batch_25 \
  --label IME \
  --output HGTD-analysis/CQC/results/1nd_batch_25
```

This example assumes the IME/vendor `sensorYields.csv` files are stored beside
the IHEP sample wafers, as in the current IHEP batch tree. If your vendor
yields are elsewhere, use that directory for the collector input and pass the
matching wafer tree with `--sample`. Then make the cross-check tables:

```bash
python3 HGTD-analysis/scirpt/summarize_sensor_yields.py \
  HGTD-analysis/CQC/results/1nd_batch_25
```

This creates:

```text
results/1nd_batch_25/
├── sensor_yields_by_grade/       # IHEP: A.csv, B.csv, C.csv
├── sensor_yields_by_grade_IME/   # IME: A.csv, B.csv, C.csv
└── yield_summary/                # IHEP vs IME counts per wafer and totals
    ├── A.csv
    ├── B.csv
    └── C.csv
```

If the IME yields are already arranged as a per-wafer results directory, use
that directory for the second collector's input. Both collector invocations
must use the same batch's wafers so the summary compares like-for-like.

## Package results for transfer

Run post-processing first so the archive contains the per-wafer plots and CSVs
as well as the IHEP/IME grade tables and cross-check. From the repository
root, create the ZIP beside the batch directory:

```bash
cd HGTD-analysis/CQC/results
zip -r 1nd_batch_25_results.zip 1nd_batch_25
```

Replace `1nd_batch_25` with the batch directory to transfer. The ZIP contains
the complete result tree and can be copied to the receiving site. Check the
archive listing before transfer:

```bash
unzip -l 1nd_batch_25_results.zip
```

Do not put the ZIP inside the directory being zipped; keep it beside that
directory so it cannot include itself.
