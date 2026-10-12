# CQC 晶圆 IV 分析流程

> English version: [README.md](README.md)

本流程使用 ROOT 宏 `Card52_v3.C` 分析已解压的晶圆 IV 曲线，生成 sensor grade 和图表；随后汇总 IHEP 与 IME 的 grade，并将结果打包传输。

## 流程概览

1. 按下方目录结构准备输入数据，并解压目标 batch 的 ZIP。
2. 选择本地、IHEP 集群或 CERN 集群模式运行分析。
3. 等待所有晶圆作业完成，确认每片晶圆都有 `sensorYield.csv`。
4. 分别整理 IHEP 和 IME 的 grade，再生成两者的 grade 数量 cross-check。
5. 将结果目录压缩成 ZIP 后传输。

## 输入目录结构

`wafer_folder` 应指向一个 batch 目录。目录中每片晶圆对应一个子目录，batch 根目录包含温度表。例如：

```text
CQC_sample/
└── IHEP/
    └── 1nd_batch_25/                         # wafer_folder
        ├── wafer_temperature_template.csv     # 分析必需
        ├── B34_10/
        │   ├── 20WS0013400010.zip             # 原始压缩包
        │   ├── 20WS0013400010/                 # 解压后的输入目录，分析必需
        │   │   ├── 20WS20340010-1.csv
        │   │   ├── 20WS20340010-2.csv
        │   │   └── ...                         # 共 780 个 IV CSV
        │   ├── sensor_attributes_template_20WS0013400010.CSV
        │   ├── sensor_parts_template_20WS0013400010.CSV
        │   ├── parttree_sensor_20WS0013400010.CSV
        │   └── sensorYields.csv                # 已有的 IME/vendor 结果，
        │                                       # 仅用于 cross-check
        ├── B34_11/
        │   └── ...                             # 每片晶圆布局相同
        └── ...
```

每片晶圆必须有一个以 `20WS...` 序列号命名的解压目录；配置生成器会跳过没有该目录的晶圆。目录中是每个 sensor 每个测试列的 IV CSV：52 个 sensor × 15 列，共 780 个文件。ROOT 分析需要这些 CSV 和 batch 根目录的温度表。metadata CSV 随样本保留，用于 sensor/wafer 信息关联；已有 `sensorYields.csv` 用作 IME/vendor grade 输入。原始 ZIP 会保留。

从仓库根目录运行以下命令，并将参数替换为要处理的 batch 路径：

```bash
python3 HGTD-analysis/scirpt/unzip_cqc.py \
  CQC_sample/IHEP/1nd_batch_25
```

脚本会递归搜索指定 batch 目录，在 ZIP 所在晶圆目录旁解压，并跳过已解压的 ZIP。其他示例：`CQC_sample/CERN/2nd_batch_95`。新 batch 也应保持 batch 根目录 / wafer 目录 / 序列号子目录的结构。传输到 IHEP 时，如果已包含解压目录，可以不传原始 ZIP。

## Python 和 ROOT 环境

从仓库根目录创建并激活虚拟环境，然后安装仓库 requirements 中的 Python 依赖：

```bash
python3 -m venv HGTD-analysis/.venv
source HGTD-analysis/.venv/bin/activate
python -m pip install --upgrade pip
python3 -m pip install -r HGTD-analysis/requirements.txt
```

在激活的虚拟环境中运行后续命令。完成后执行 `deactivate` 退出环境。ROOT 是系统依赖，不包含在 `requirements.txt` 中；请确保 `root` 命令可用（CERN 作业使用 ROOT 6.40）。

## 选择运行模式

| 模式 | 运行位置 | 提交方式 | 结果位置 |
|---|---|---|---|
| Local | 本地工作站 | `run_all.sh` 顺序运行各片晶圆 | `HGTD-analysis/CQC/results/<wafer>/` |
| IHEP cluster | IHEP 共享文件系统 | 一次提交一个 `hep_sub` 作业簇，每个 ProcId 对应一片晶圆 | 共享文件系统上的 `HGTD-analysis/CQC/results/<wafer>/` |
| CERN cluster | CERN HTCondor EosSubmit | 使用 `condor_submit`，每片晶圆一个作业；输入和输出直接读写 EOS | 所选配置中 `eos_output_dir/<wafer>/` |

仓库中已跟踪的生成器配置如下：

| 配置文件 | 模式和样本 |
|---|---|
| `config_generator_local.yaml` | Local；当前指向 IHEP `1nd_batch_25` |
| `config_generator.yaml` | IHEP cluster；当前指向 IHEP `1nd_batch_25` |
| `config_generator_cern.yaml` | CERN cluster；CERN `2nd_batch_95` |

切换 batch 时，同时检查并更新 `wafer_folder` 和 `temp_file`。Local 和 IHEP 模式还需将 `main_path` 设置为运行机器上的仓库绝对路径；输出、配置、作业脚本和日志路径相对于 `main_path`。CERN 模式中的 `eos_input_dir`、`eos_output_dir` 和 `venv_path` 是写入生成作业脚本的绝对 EOS 路径，按实际 CERN EOS 位置设置。

从仓库根目录生成配置和提交文件，按运行模式选择配置文件：

```bash
python3 HGTD-analysis/CQC/generate_configs.py \
  HGTD-analysis/CQC/config_generator_local.yaml
```

生成器会扫描 `wafer_folder` 下含有已解压 `20WS...` 子目录的晶圆目录。生成配置前先解压目标 batch。

## 本地运行

生成 Local 配置后，顺序运行所有晶圆：

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

单独运行一片晶圆：

```bash
python3 HGTD-analysis/CQC/run_local.py \
  HGTD-analysis/CQC/configs/config_B34_2.yaml
```

## IHEP 集群提交

先将仓库和样本传到 IHEP worker 可访问的共享路径。macOS 创建 tar 包时可排除扩展属性和原始 ZIP（作业读取的是解压后的 CSV）：

```bash
tar czf HGTD_sensor.tar.gz --no-xattrs --no-mac-metadata \
  --exclude='*.zip' -C /path/to/parent HGTD_sensor
```

在 IHEP 上解包后，将 `config_generator.yaml` 中的 `main_path` 设为共享路径，并检查 `wafer_folder`、`temp_file` 是否指向目标 batch。然后生成并提交：

```bash
python3 HGTD-analysis/CQC/generate_configs.py \
  HGTD-analysis/CQC/config_generator.yaml
bash HGTD-analysis/CQC/jobs/run_all.sh
```

IHEP 模式为发现的每片晶圆创建一个 ProcId。生成的脚本将 ProcId 映射到对应配置。使用 `hep_q -u` 查看队列；标准输出和错误日志位于配置的 `log_folder`，文件名为 `job_<ProcId>.out` 和 `job_<ProcId>.err`。

## CERN 集群提交

CERN 模式通过 EOS 绝对路径读写输入和结果。登录节点上的生成器使用 `config_generator_cern.yaml` 生成 `filelist.txt`、`job.sh`、`cern_batch.sub` 和 `src.tar`。`src.tar` 是分析宏和 runner 的代码快照。将这些生成文件传到对应 campaign 的 EOS 提交目录，并确保该目录有 `out/` 和 `logs/` 子目录，再从提交目录运行：

```bash
cd /eos/user/<user>/HGTD/CQC_batch
condor_submit cern_batch.sub
```

每片晶圆对应一个作业。作业从 `eos_input_dir` 读取已解压 CSV 和温度表，并将结果写到 `eos_output_dir/<wafer>/`。检查 Condor 队列以及提交目录中的 `.out`、`.err` 文件。如果 `Card52_v3.C` 或 `run_local.py` 有更新，重新生成并传输 `src.tar`；已提交作业使用提交时收到的代码快照。

## 结果目录

每个成功的晶圆作业生成类似以下目录：

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

当前输出汇总文件名为 `sensorYield.csv`；汇总脚本也兼容历史文件名 `sensorYields.csv` 和以序列号命名的 CSV。每片 wafer 的 ROOT 文件保存 `ChannelResults` TTree、wafer 级 map，并在 `Sensors/Sensor_XX/` 下保存 `VbdMap`、`LeakageMap`、`VbdHist` 和 `LeakageHist`。`ChannelResults` 每个 channel 一条 entry，仅包含 `sensor_id`、`channel_id`、`vbd_at_test_temperature_V`、`vbd_corrected_20C_V` 和 `leakage_current_A`。Leakage current 是 CQC 算法在 probe 电压（该 sensor 测试温度下最小 Vbd 的 0.8 倍）处对该 channel 电流插值得到的值。`sensorYield.csv` 仍是 summary 表。开始后处理前，检查作业日志并确认每片晶圆的汇总 CSV 均已生成。CERN 的 batch 结果目录由 `eos_output_dir` 指定；Local 和 IHEP 可通过生成器配置中的 `output_path` 设置 batch 专属目录。

## IHEP 与 IME yield 后处理

相对路径继续以 `/eos/user/l/liaoc/public/HGTD_sensor` 为基准。
输入选择一个批次，其下直接包含 `Bxx_wafer/`；sample 中的 `Bxx-wafer`
会统一为相同身份。支持 `sensorYield.csv`、`sensorYields.csv` 和
`20WS<serial>.csv`，同一晶圆有多个候选表时明确报错。

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

collector 输出 `sensor_yields_by_grade/{A,B,C}.csv` 及对应 IME 目录；
仅 B/B1/B2 合并为 B，未知状态和重复身份报错。
支持只有 `Sensor,Final_Status` 的 vendor 表，缺失的物理指标保持为空。
summary 输出 `yield_summary/{A,B,C}.csv`，比较输出成对的
`sensor_yield_differences.csv`，两侧 wafer/sensor 身份集合必须一致。
ROOT 导出、SQC 汇总及逐像素 Vbd 与求和电流 Vbd 的区别见
[当前 results 后处理审核](../doc/POST_PROCESSING_AUDIT_CN.md)。

## CQC 的 sensor 和 channel Vbd 图

使用统一入口 `plot_vbd.py`，由 `--level` 选择输入格式和绘图流程。
`sensor-level` 输入 CQC results 目录，递归读取每片 wafer 的
`sensorYield.csv`（兼容历史文件名 `sensorYields.csv`），分别绘制 Vbd
average、minimum 和 RMS 三张 PDF。默认输出到输入目录下的
`vbd_sensor_plots/`；`--output` 用于指定输出目录：

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/CQC/plot_vbd.py \
  CQC_results/CERN/2nd_batch_95_IHEP \
  --level sensor-level \
  --output HGTD-analysis/CQC/plots/2nd_batch_sensor_vbd
```

`channel-level` 输入一片 wafer 的 ROOT 文件，从 `ChannelResults` TTree
读取修正到 20°C 的 `vbd_corrected_20C_V`，绘制所有 channel 的 Vbd 直方图。
默认输出为 ROOT 文件旁的 `<wafer>_vbd_channel-level.pdf`；此模式下
`--output` 接收 PDF 文件路径：

```bash
HGTD-analysis/.venv/bin/python HGTD-analysis/CQC/plot_vbd.py \
  CQC_results/CERN/2nd_batch_95_IHEP/B31_10/B31_10.root \
  --level channel-level \
  --output HGTD-analysis/CQC/plots/B31_10_channel_vbd.pdf
```

ROOT 文件由 Python 依赖 `uproot` 读取；安装 `HGTD-analysis/requirements.txt`
后即可在分析虚拟环境运行。两种模式的图都使用 mplhep ATLAS style 并标注
`HGTD Internal`。

## 打包传输结果

先完成后处理，再将每片晶圆的图表、CSV、IHEP/IME grade 表和 cross-check 一并压缩。从仓库根目录执行：

```bash
cd HGTD-analysis/CQC/results
zip -r 1nd_batch_25_results.zip 1nd_batch_25
```

将 `1nd_batch_25` 替换为要传输的 batch 目录。ZIP 会创建在 batch 目录旁，可直接传给接收方。传输前可检查压缩包目录：

```bash
unzip -l 1nd_batch_25_results.zip
```

不要将 ZIP 放在待压缩的 batch 目录内，以免把压缩包本身再次加入归档。
