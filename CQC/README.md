# HGTD Sensor IV Analysis

> 中文版: [README_CN.md](README_CN.md)

This directory analyzes wafer-level 15×1 IV test data with the ROOT macro
`Card52_v3.C`.

## 1. Data layout

`CQC_sample/2nd_batch_95/` contains 95 wafer directories, grouped into four
batches: B23, B31, B33 and B36.

Each wafer directory typically contains:

```text
20WS0013300017.zip                 # original ZIP, always kept
20WS0013300017/                    # 780 extracted IV CSVs (folder named after the ZIP)
sensorYields.csv                   # existing analysis result (unified naming)
sensor_attributes_template_*.CSV   # sensor serial number and wafer position
sensor_parts_template_*.CSV        # sensor serial number and batch
parttree_sensor_*.CSV              # wafer–sensor parent relation
```

Extraction is done by `script/unzip_cqc.py` (in place, ZIPs kept, idempotent):

```bash
python3 script/unzip_cqc.py
```

The analysis code in this directory only reads the extracted CSVs; it never
unzips anything.

### Raw ZIP

Each ZIP holds 780 IV curves of one wafer:

```text
52 sensors × 15 columns each = 780 CSVs
```

Raw file format:

```csv
Voltage(V),Current(A)
0.0,1.43e-09
2.0,6.375e-09
```

File names look like:

```text
20WS2033001701-1.csv
```

where `01` is the sensor number and `-1` the tested column.

### Wafer-level tables

Three files in the `2nd_batch_95/` root record:

- `wafer_temperature_template.csv`: test temperature per wafer;
- `wafer_attributes_template.csv`: good-sensor count, thickness, resistivity, appearance;
- `wafer_parts_template.csv`: wafer serial, batch, production date, remarks.

## 2. Environment

Requirements:

- ROOT (verified with ROOT 6.40);
- Python 3;
- PyYAML:

```bash
pip install pyyaml
```

## 3. Generate per-wafer configs

Edit `config_generator.yaml`:

```yaml
main_path: /path/to/HGTD_sensor
mode: local                 # local or ihep
wafer_folder: CQC_sample/2nd_batch_95
config_folder: HGTD-analysis/CQC/configs
script_folder: HGTD-analysis/CQC/jobs
log_folder: HGTD-analysis/CQC/job_logs
temp_file: CQC_sample/2nd_batch_95/wafer_temperature_template.csv
root_macro: HGTD-analysis/CQC/Card52_v3.C
output_path: HGTD-analysis/CQC/results
hep_sub_options: -wt short
```

All paths except `main_path` are relative to `main_path`.

Run:

```bash
python3 HGTD-analysis/CQC/generate_configs.py HGTD-analysis/CQC/config_generator.yaml
```

The script walks the wafer directories under `wafer_folder`, locates the
extracted data subfolder (`20WS*`) in each, and generates:

```text
HGTD-analysis/CQC/configs/config_B33_17.yaml
HGTD-analysis/CQC/configs/config_B23_17.yaml
...
```

## 4. Local run

### Single wafer

```bash
python3 HGTD-analysis/CQC/run_local.py HGTD-analysis/CQC/configs/config_B33_17.yaml
```

`run_local.py` automatically:

1. reads the temperature for the wafer from the temperature table;
2. reads the CSVs directly from the extracted data subfolder;
3. runs `Card52_v3.C`;
4. organizes the output images per sensor.

Run all wafers:

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

In local mode, `run_all.sh` runs all generated configs sequentially.

## 5. IHEP cluster submission

Before submitting, transfer the sample to the IHEP cluster. On macOS use:

```bash
tar czvf target.tar.gz --no-xattrs --no-mac-metadata --exclude='*.zip' /path/to/source
```

otherwise the macUSD metadata files get transferred too; on Windows use the
normal packaging command. Note the `--exclude='*.zip'` (the extracted CSVs
already sit in the tree).

For submission see the [IHEP HTCondor/HepJob
documentation](http://afsapply.ihep.ac.cn/cchelp/zh/local-cluster/jobs/HTCondor/).

Switch `config_generator.yaml` to:

```yaml
mode: ihep
```

and set `main_path` to a shared path visible from the worker nodes, e.g.:

```yaml
main_path: /cefs/your/path/HGTD_sensor
```

Regenerate:

```bash
python3 HGTD-analysis/CQC/generate_configs.py HGTD-analysis/CQC/config_generator.yaml
```

IHEP mode generates `HGTD-analysis/CQC/jobs/run_all.sh`. The script calls
`hep_sub` exactly once, creating one job cluster with 95 ProcIds via `-n 95`:

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

Each ProcId maps to one wafer through the wafer array inside the script, which
selects the matching `config_Bxx_xx.yaml`. Stdout/stderr go to:

```text
HGTD-analysis/CQC/job_logs/job_0.out
HGTD-analysis/CQC/job_logs/job_0.err
...
```

Check jobs:

```bash
hep_q -u
```

## 6. Output structure

The output directory is:

```text
HGTD-analysis/CQC/results/B33_17/
├── sensorYield.csv
├── VbdMap.png
├── LKGnoMap.png
├── IV_Full.png
├── Sensor_Grade_Map.png
├── run.log
├── sensor_1/
│   ├── VMap_Sensor_1.png
│   ├── BVHist_Sensor_1.png
│   ├── Leakage_Current_Sensor_1.png
│   ├── Leakage_Current_Full_Sensor_1.png
│   └── IDist_Sensor_1.png
└── sensor_52/
    └── ...
```

Global result files (without a sensor number) sit at the wafer result root;
the 5 per-sensor images go into the corresponding `sensor_N` directory.

The analysis code no longer produces any unzip directory; the results
directory is in `.gitignore`.
