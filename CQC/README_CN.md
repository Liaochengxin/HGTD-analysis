# HGTD Sensor IV Analysis

> English version: [README.md](README.md)

本目录使用 ROOT 宏 `Card52_v3.C` 分析晶圆的 15×1 IV 测试数据。

## 1. 数据结构

`CQC_sample/` 按提交地点分组：`CQC_sample/CERN/{pilot_batch_17, 1nd_batch_100, 2nd_batch_95}`（CERN lxplus 批处理）和 `CQC_sample/IHEP/1nd_batch_25`（IHEP 集群，B34/B35 batch）。每个 batch 目录下是各晶圆目录（2nd batch 分为 B23、B31、B33 和 B36 四个 batch）。

每个晶圆目录通常包含：

```text
20WS0013300017.zip                 # 原始 ZIP，始终保留
20WS0013300017/                    # 解压后的 780 个 IV CSV（目录名 = ZIP 名）
sensorYields.csv                   # 已有的分析结果（统一命名）
sensor_attributes_template_*.CSV   # Sensor 序列号和晶圆位置
sensor_parts_template_*.CSV        # Sensor 序列号和 batch
parttree_sensor_*.CSV               # Wafer 与 Sensor 的父子关系
```

解压由 `scirpt/unzip_cqc.py` 统一完成（原地解压，保留 ZIP，幂等）：

```bash
python3 HGTD-analysis/scirpt/unzip_cqc.py
```

本目录的分析代码只读取已解压的 CSV，不做任何解压。

### 原始 ZIP

每个 ZIP 包含一片晶圆的 780 条 IV 曲线：

```text
52 个 sensor × 每个 sensor 15 列 = 780 个 CSV
```

原始文件格式为：

```csv
Voltage(V),Current(A)
0.0,1.43e-09
2.0,6.375e-09
```

文件名类似：

```text
20WS2033001701-1.csv
```

其中 `01` 是 Sensor 编号，`-1` 是测试列编号。

### 晶圆级总表

`CERN/2nd_batch_95/` 根目录下的三个文件分别记录：

- `wafer_temperature_template.csv`：每片晶圆的测试温度；
- `wafer_attributes_template.csv`：good sensor 数量、厚度、电阻率和外观等晶圆属性；
- `wafer_parts_template.csv`：晶圆序列号、batch、生产日期和备注。

## 2. 环境

需要：

- ROOT（本机已验证 ROOT 6.40）；
- Python 3；
- PyYAML：

```bash
pip install pyyaml
```

## 3. 生成每片晶圆的配置

每个运行目标一份生成器 yaml，按分析运行的位置选择，批次或布局变化后重新生成：

| yaml | mode | 运行目标 |
|---|---|---|
| `config_generator_local.yaml` | `local` | 本机顺序运行 |
| `config_generator.yaml` | `ihep` | IHEP 集群，`hep_sub` |
| `config_generator_cern.yaml` | `cern` | lxplus EosSubmit，第二批 |
| `config_generator_cern_1st.yaml` | `cern` | lxplus EosSubmit，第一批 |
| `config_generator_cern_pilot.yaml` | `cern` | lxplus EosSubmit，pilot 批 |

本地运行编辑 `config_generator_local.yaml`：

```yaml
main_path: /path/to/HGTD_sensor
mode: local
wafer_folder: CQC_sample/IHEP/1nd_batch_25
config_folder: HGTD-analysis/CQC/configs
script_folder: HGTD-analysis/CQC/jobs
run_local: HGTD-analysis/CQC/run_local.py
temp_file: CQC_sample/IHEP/1nd_batch_25/wafer_temperature_template.csv
root_macro: HGTD-analysis/CQC/Card52_v3.C
output_path: HGTD-analysis/CQC/results
```

除 `main_path` 外，其余路径均相对于 `main_path`，因此整个代码树放在哪里都可以——把 `main_path` 指向本仓库的根目录即可，其余不用动。各路径键的含义：

- `main_path` — 运行生成器的机器上 HGTD_sensor 代码树根目录的绝对路径（本地磁盘、集群 home 等）；
- `wafer_folder` — 存放各晶圆目录的 batch 目录，如 `CQC_sample/IHEP/1nd_batch_25` 或 `CQC_sample/CERN/2nd_batch_95`（相对于 `main_path`）；
- `temp_file` — 该 batch 的 `wafer_temperature_template.csv`，位于 batch 根目录、与晶圆目录同级（相对于 `main_path`）；换批次时把 `wafer_folder` 和 `temp_file` 一起改；
- `config_folder` / `script_folder` / `log_folder` / `output_path` — 生成的配置、提交脚本、作业日志、结果的存放位置（相对于 `main_path`）。

cern 模式是例外：作业直接读写 EOS，`eos_input_dir` / `eos_output_dir` / `venv_path` 是 `/eos/user/<user>/...` 形式的绝对路径，生成时直接写进 `job.sh`。

执行：

```bash
python3 HGTD-analysis/CQC/generate_configs.py HGTD-analysis/CQC/config_generator_local.yaml
```

脚本会遍历 `wafer_folder` 下的晶圆目录，定位其中已解压的数据子目录（`20WS*`），并生成：

```text
HGTD-analysis/CQC/configs/config_B33_17.yaml
HGTD-analysis/CQC/configs/config_B23_17.yaml
...
```

## 4. 本地运行

### 单片运行

```bash
python3 HGTD-analysis/CQC/run_local.py HGTD-analysis/CQC/configs/config_B33_17.yaml
```

`run_local.py` 会自动：

1. 读取温度表中的对应温度；
2. 直接从解压好的数据子目录读取 CSV；
3. 调用 `Card52_v3.C`；
4. 按 Sensor 整理图片结果。

运行全部晶圆：

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

本地模式下，`run_all.sh` 会按顺序运行全部生成的配置。

## 5. 高能所 IHEP 批量提交

在批量提交之前，你需要把sample传输到ihep cluster上，如果你使用mac，可以用下面命令，否则会把mac打包数据也传输到clutser上, 如果是windows就用普通的打包命令就好了。注意排除 zip（解压后的 CSV 已随目录树就位）：

```bash
tar czvf target.tar.gz --no-xattrs --no-mac-metadata --exclude='*.zip' /path/to/source
```

提交方式参考[高能所 HTCondor/HepJob 文档](http://afsapply.ihep.ac.cn/cchelp/zh/local-cluster/jobs/HTCondor/)。

把 `config_generator.yaml` 中的模式改为：

```yaml
mode: ihep
```

并把 `main_path` 改成计算节点可访问的共享路径，例如：

```yaml
main_path: /cefs/your/path/HGTD_sensor
```

重新生成：

```bash
python3 HGTD-analysis/CQC/generate_configs.py HGTD-analysis/CQC/config_generator.yaml
```

IHEP 模式会生成一个 `HGTD-analysis/CQC/jobs/run_all.sh`。该脚本只执行一次 `hep_sub`，通过 `-n 95` 创建一个包含 95 个 ProcId 的作业簇：

```bash
bash HGTD-analysis/CQC/jobs/run_all.sh
```

每个 ProcId 对应一片晶圆，脚本内部通过 wafer 数组映射到相应的 `config_Bxx_xx.yaml`。标准输出和错误日志写入：

```text
HGTD-analysis/CQC/job_logs/job_0.out
HGTD-analysis/CQC/job_logs/job_0.err
...
```

查询作业：

```bash
hep_q -u
```

## 6. 输出结构

输出目录为：

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

不带 Sensor 编号的全局结果文件放在晶圆目录根部；带 Sensor 编号的 5 张图放入对应的 `sensor_N` 目录。

CERN 批处理会按批次分开保存结果：`CQC/results/1st_batch_100/<wafer>/`、
`CQC/results/2nd_batch_95/<wafer>/` 和 `CQC/results/pilot_batch_17/<wafer>/`。

分析代码不再产生解压目录；结果目录已加入 `.gitignore`。
