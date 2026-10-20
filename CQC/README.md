# CQC sensor IV workflow

> 中文说明见 [README_CN.md](README_CN.md).

This workflow runs `Card52_v3.C` on wafer IV curves, collects sensor grades,
compares IHEP and IME yields, and packages the outputs for transfer.

## Workflow at a glance

1. Prepare the sample tree (the per-wafer raw ZIPs are the input; local and
   CERN modes additionally need each ZIP extracted once).
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
        │   │                                   # for local/CERN modes only
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

The batch root must contain `wafer_temperature_template.csv`. The raw input of
each wafer is its `20WS...` ZIP: 52 sensors × 15 columns = 780 per-column IV
CSVs, which is all the ROOT analysis needs besides the temperature table. The
metadata CSVs are retained with the sample for sensor/wafer bookkeeping, while
`sensorYields.csv` is the existing IME/vendor result used by the optional
yield cross-check.

How the ZIPs are consumed depends on the mode. IHEP mode reads the ZIPs
directly — one per wafer, identified by file name alone (ZIP stem = serial,
parent directory = wafer name); the job wrapper extracts the ZIP into node
scratch, validates the 780 CSVs, and removes the scratch copy afterwards, so
no extraction on the submission side is needed. Local and CERN modes still
read the extracted `20WS...` subdirectories; extract them once with:

```bash
python3 HGTD-analysis/scirpt/unzip_cqc.py \
  CQC_sample/IHEP/1nd_batch_25
```

Pass the batch directory as the positional argument; the helper searches it
recursively, extracts ZIPs beside their wafer directories, and skips archives
that are already extracted. Change the argument to the batch being processed,
for example `CQC_sample/CERN/2nd_batch_95`. For a new batch, preserve the same
batch-root / wafer-directory / serial-subdirectory structure. When
transferring the sample to IHEP, the ZIPs must be included; the extracted
directories can be omitted.

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

The generator scans the batch for per-wafer ZIPs in IHEP mode, and wafer
folders containing an extracted `20WS...` directory in local and CERN modes
(extract the sample data first in those modes).

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
Keep the original per-wafer ZIPs — they are what the jobs read; the extracted
per-serial directories are not needed for IHEP runs. For a macOS-created
tarball, omit extended attributes:

```bash
tar czf HGTD_sensor.tar.gz --no-xattrs --no-mac-metadata \
  -C /path/to/parent HGTD_sensor
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

IHEP mode creates one `hep_sub` cluster with one process per discovered wafer
ZIP. The generated `run_all.sh` maps each process ID to the corresponding
wafer, and each job's `job.sh` extracts that wafer's ZIP into node scratch
(`$TMPDIR`), validates the 780 CSVs, and removes the scratch copy when the
job exits — a corrupt or incomplete ZIP fails the job with an explicit
message. Check the queue with `hep_q -u`; stdout and stderr are written under
the configured `log_folder` as `job_<ProcId>.out` and `job_<ProcId>.err`.

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
├── <wafer>.root
├── VbdMap.png
├── LKGnoMap.png
├── IV_Full.png
├── Sensor_Grade_Map.png
├── run.log
└── sensor_1/ ... sensor_52/
```

The output summary is named `sensorYield.csv` by current runs; the collector
also accepts historical `sensorYields.csv` and serial-number CSV filenames.
Each wafer ROOT file stores a `ChannelResults` TTree with one entry per
channel, the wafer-level maps, and the `VbdMap`, `LeakageMap`, `VbdHist`, and
`LeakageHist` objects under `Sensors/Sensor_XX/`. The tree contains
`sensor_id`, `channel_id`, `vbd_at_test_temperature_V`,
`vbd_corrected_20C_V`, and `leakage_current_A`. Leakage current is the
per-channel interpolated current at the CQC probe voltage (`0.8 ×` the
sensor's minimum Vbd at test temperature). `sensorYield.csv` remains the
summary table.
Review job logs and ensure the expected per-wafer summary CSVs exist before
starting post-processing. CERN mode's `<batch>` directory is the configured
EOS output directory; local and IHEP modes can use a batch-specific output
directory by setting `output_path` in their generator config accordingly.

## Post-process IHEP and IME yields

Relative collector, comparison and yield-summary paths remain rooted at
`/eos/user/l/liaoc/public/HGTD_sensor`. Select a single batch with immediate
`Bxx_wafer/` directories; `Bxx-wafer` sample names are normalized to the same
identity. Yield tables may be named `sensorYield.csv`, `sensorYields.csv`, or
`20WS<serial>.csv`; multiple candidates are an error. `--sample` selects the
matching extracted `20WS...` serial directories.

```bash
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  CQC_results/CERN/2nd_batch_95_IHEP \
  --sample CQC_sample/CERN/2nd_batch_95
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  CQC_sample/CERN/2nd_batch_95 --label IME \
  --output CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/scirpt/summarize_sensor_yields.py \
  CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/CQC/compare_sensor_yields.py \
  CQC_results/CERN/2nd_batch_95_IHEP \
  --ime CQC_sample/CERN/2nd_batch_95
```

The collector writes `sensor_yields_by_grade/{A,B,C}.csv` and its IME counterpart.
Only B/B1/B2 are grouped into B; unknown statuses and duplicate identities fail.
The summary writes `yield_summary/{A,B,C}.csv`; comparisons require matching
wafer/sensor sets and write paired rows to `sensor_yield_differences.csv`.
See [the current results audit](../doc/POST_PROCESSING_AUDIT_CN.md) for ROOT
exports, SQC summaries, and the distinction between individual-pixel Vbd and
Vbd computed from summed pixel currents.

## CQC sensor and channel Vbd plots

Use the single entry point `plot_vbd.py`; `--level` selects both the input
format and plotting path. For `sensor-level`, pass a CQC results directory.
The script recursively reads each wafer's `sensorYield.csv` (also accepting
the historical `sensorYields.csv`) and creates separate Vbd average, minimum,
and RMS PDFs. The default output directory is
`<input directory>/vbd_sensor_plots/`; `--output` selects another directory:

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/CQC/plot_vbd.py \
  CQC_results/CERN/2nd_batch_95_IHEP \
  --level sensor-level \
  --output HGTD-analysis/CQC/plots/2nd_batch_sensor_vbd
```

For `channel-level`, pass one wafer ROOT file. The script reads the corrected-
to-20°C `vbd_corrected_20C_V` branch from its `ChannelResults` TTree and plots
the Vbd distribution across channels. By default, the PDF is written beside
the ROOT file as `<wafer>_vbd_channel-level.pdf`; `--output` takes a PDF file
path:

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/CQC/plot_vbd.py \
  CQC_results/CERN/2nd_batch_95_IHEP/B31_10/B31_10.root \
  --level channel-level \
  --output HGTD-analysis/CQC/plots/B31_10_channel_vbd.pdf
```

The ROOT file is read with `uproot`, included in `HGTD-analysis/requirements.txt`.
Both modes use mplhep's ATLAS style and label the plots `HGTD Internal`.

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
