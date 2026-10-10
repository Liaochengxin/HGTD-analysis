# SQC sensor 交叉校验流程

> English version: [README.md](README.md)

本流程使用 `temp_vbdmin_cross_toIME_v2.C` 将针台 SQC 数据（每片 sensor 225 个 pad）与探卡 CQC 数据（15 个通道）进行比较。本地运行和集群作业使用同一份 sensor 任务计划。

## 流程

1. 按下方目录格式准备针台和探卡数据。
2. 在 `config.yaml` 中设置路径、温度和运行模式。
3. 用 `--dry-run` 预览 sensor 与 CQC 的匹配结果。
4. 选择本地顺序运行，或提交到 IHEP / CERN 集群，每个 sensor 一个作业。
5. 集群任务结束后，收集各 sensor 的 `crosscheck.csv`，生成统一的 `summary_all.csv`。

## 输入目录结构

`sqc_folder` 直接指向本次要处理的批次目录。脚本只在这个目录下匹配 `B*/W*_P*/SweepVoltage0`，不会扫描共同父目录中的其他批次。切换批次时，只需将 `config.yaml` 中的 `sqc_folder` 改为对应目录：

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

CQC 目录中需有解压后的逐晶圆数据和温度表：

```text
CQC_sample/CERN/2nd_batch_95/               # cqc_folder
├── wafer_temperature_template.csv
└── B31_15/
    └── 20WS0013100015/
        ├── 20WS2031001501-1.csv
        ├── ...
        └── 20WS2031001501-15.csv
```

每片 CQC 晶圆包含 52 个 sensor × 每个 sensor 15 个通道 CSV。`cqc_fallback_folder` 可指向旧版解压数据。匹配顺序为：`cqc_folder` 中精确匹配 wafer 和 sensor；fallback 目录中精确匹配 sensor；最后使用找到的 CQC 数据作 placeholder。计划会打印每个 sensor 的数据来源。运行前要检查这些来源：placeholder 可用于检查宏能否运行，但其 ProbeCard 结果不是真实交叉校验。如果完全找不到 CQC 文件，该 sensor 会跳过。

若温度表中缺少某片 wafer 的温度，计划会发出警告并使用 `Tp=20°C`。

## 环境和配置

生成计划和作业需要 Python 3 与 PyYAML。从仓库根目录创建虚拟环境并安装依赖：

```bash
python3 -m venv HGTD-analysis/.venv
source HGTD-analysis/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r HGTD-analysis/requirements.txt
```

本地运行使用本机已有 ROOT，不加载 ATLAS 环境。集群作业会加载 ATLAS 环境，并使用与 CQC 相同的 ROOT 版本：

```bash
export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase
source "$ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh"
lsetup 'root 6.40.02-x86_64-el9-gcc15-opt'
```

`config.yaml` 中 `main_path` 是绝对路径，其余数据、宏、作业和输出路径相对于它：

| 配置项 | 用途 |
|---|---|
| `mode` | 集群提交模式：`ihep` 或 `cern`；本地直接运行 `run_all_sqc.py` |
| `sqc_folder` | 本次处理的针台批次目录，例如 `SQC_sample/2nd_batch_SQC` |
| `cqc_folder` | 首选的解压 CQC batch，包含温度表 |
| `cqc_fallback_folder` | 可选的旧 CQC 数据，用于精确匹配或 placeholder |
| `temp_file` | CQC 晶圆温度表 |
| `tn` | 针台温度（°C），当前假设为 20°C |
| `root_version` | 集群 worker 加载的 ROOT 版本，与 CQC 一致 |
| `output_path` | 本地和集群共用的结果目录 |
| `job_folder` | 生成的作业提交包目录；其最后一级目录名默认作为 CERN HTCondor batch 名称 |

当前 CQC 样本路径是 `CQC_sample/CERN/2nd_batch_95`；切换 batch 时同步修改 `cqc_folder` 和 `temp_file`。仓库中的配置目前设置为 CERN HTCondor 模式（`mode: cern`），使用 `flavour: microcentury`，`main_path` 指向集群共享文件系统。本地运行时，将 `main_path` 改成本地仓库根目录；`run_all_sqc.py` 不要求集群 mode 设置。

## 预览或本地运行

先预览计划，不执行 ROOT：

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py \
  HGTD-analysis/SQC/config.yaml --dry-run
```

`config.yaml` 中当前的 `sqc_folder` 指向第二批。要处理第一批，先将其改为 `SQC_sample/1st_batch_SQC`。运行时不再使用批次或 sensor 筛选参数。

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py \
  HGTD-analysis/SQC/config.yaml --dry-run
```

结果按 sensor 的 batch 编号分组。每片 sensor 的目录包含 `crosscheck.csv`、`run.log` 和图片；任务清单与总汇总表保留在 `output_path` 根目录：

```text
results/
├── B15/
│   └── W11-P2/
├── B18/
│   └── W01-P7/
├── sensor_plan.csv
└── summary_all.csv
```

`sensor_plan.csv` 记录匹配到的 CQC 来源和温度；`summary_all.csv` 递归汇总各个 `Bxx` 目录中的 sensor 结果。

## 提交到 IHEP

将输入数据放到 worker 可访问的共享路径后，在 IHEP 机器上生成作业包。确认配置中的 `mode: ihep`、`main_path` 和批次级 `sqc_folder` 指向最终共享路径。生成作业前，先在配置中选定要提交的批次目录：

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py \
  HGTD-analysis/SQC/config.yaml
cd HGTD-analysis/SQC/jobs
./submit_all.sh
```

作业包包含 `sensors.list`、`job.sh`、`submit_all.sh` 和 `collect_results.py`。一次 `hep_sub` 提交为每个 sensor 创建一个 ProcId。作业初始化 ATLAS/ROOT 环境，运行一个 sensor，并将结果写入共享的 `output_path`。用 `hep_q -u` 查看作业；调度器日志在 `job_folder/logs/`。所有作业结束后，从作业目录运行：

```bash
python3 collect_results.py
```

## 提交到 CERN EosSubmit

将 SQC、CQC 数据、仓库和输出放在 CERN worker 可访问的路径上（通常为 EOS）。配置 `mode: cern`，并将 `main_path`、批次级 `sqc_folder`、`cqc_folder`、`temp_file` 和 `output_path` 改为对应路径。生成作业前，在配置中选定要提交的批次目录：

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py \
  HGTD-analysis/SQC/config.yaml
cd HGTD-analysis/SQC/jobs
./submit_all.sh
```

生成文件包括 `sensors.list`、`job.sh`、`cern_batch.sub`、`source.tar` 和 `collect_results.py`。`source.tar` 固定本次提交使用的 ROOT 宏；worker 通过配置的 EOS 路径读输入、写结果。每个 sensor 对应一个 Condor 作业。用 `condor_q` 查看状态；作业结束后，在生成的作业目录运行 `python3 collect_results.py`。

默认使用 `job_folder` 最后一级目录名作为 HTCondor batch 名称，可通过 `condor_q -batch` 查看。可选参数 `--jobs NAME` 可以覆盖这个名称。

## 计算内容和结果解读

宏对每个探卡通道以 7.5 µA 为阈值，对每个针台 pad 以 0.5 µA 为阈值，通过线性插值计算 Vbd，并用 `Vbd(20°C) = Vbd − (T−20) × 1.1 V/°C` 校正到 20°C。随后分别在 `0.8 × VbdMin` 偏压下计算漏电流，并生成 Vbd / 漏电流地图、直方图、I-V 叠图和 `crosscheck.csv`。

`crosscheck.csv` 包含 `ProbeCard`、`Needle`、`Needle(inner)` 和 `Needle(inner2)` 四组。`Valid` 表示落在 165–195 V 范围内的数量（ProbeCard 为 15 个通道，Needle 为 225 个 pad），不代表良好 pad 比例。当前 `tn: 20.0` 是针台温度假设；若有实测温度，应更新后重新运行。

`process_perpad.C`、`run.C` 和 `PlotSensorVbd_multibatches.C` 是独立的旧版绘图/求和工具，不属于上述批量工作流。
