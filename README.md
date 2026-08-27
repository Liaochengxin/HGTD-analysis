# HGTD Sensor IV Analysis

本目录使用 ROOT 宏 `Card52_v3.C` 分析晶圆的 15×1 IV 测试数据。

## 1. 数据结构

`2nd_batch_95/` 中共有 95 个晶圆目录，分为 B23、B31、B33 和 B36 四个 batch。

每个晶圆目录通常包含：

```text
20WS0013300017.zip
20WS0013300017.csv                 # 已有的分析结果（部分目录使用 sensorYield.csv）
sensor_attributes_template_*.CSV   # Sensor 序列号和晶圆位置
sensor_parts_template_*.CSV        # Sensor 序列号和 batch
parttree_sensor_*.CSV               # Wafer 与 Sensor 的父子关系
```

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

根目录下的三个文件分别记录：

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

编辑 `config_generator.yaml`：

```yaml
main_path: /path/to/HGTD_sensor
mode: local                 # local 或 ihep
wafer_folder: 2nd_batch_95
config_folder: analysis/configs
script_folder: analysis/jobs
log_folder: analysis/job_logs
unzip_folder: analysis/unzipped
temp_file: 2nd_batch_95/wafer_temperature_template.csv
root_macro: analysis/Card52_v3.C
output_path: analysis/results
hep_sub_options: -wt short
```

除 `main_path` 外，其余路径均相对于 `main_path`。

执行：

```bash
python3 analysis/generate_configs.py analysis/config_generator.yaml
```

脚本会遍历 `wafer_folder` 下的晶圆目录，找到其中的 ZIP，并生成：

```text
analysis/configs/config_B33_17.yaml
analysis/configs/config_B23_17.yaml
...
```

## 4. 本地运行

### 单片运行

```bash
python3 analysis/run_local.py analysis/configs/config_B33_17.yaml
```

`run_local.py` 会自动：

1. 读取温度表中的对应温度；
2. 将 ZIP 解压到配置中的 `unzip_path`；
3. 调用 `Card52_v3.C`；
4. 按 Sensor 整理图片结果。

运行全部晶圆：

```bash
bash analysis/jobs/run_all.sh
```

本地模式下，`run_all.sh` 会按顺序运行全部生成的配置。

## 5. 高能所 IHEP 批量提交

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
python3 analysis/generate_configs.py analysis/config_generator.yaml
```

IHEP 模式会生成一个 `analysis/jobs/run_all.sh`。该脚本只执行一次 `hep_sub`，通过 `-n 95` 创建一个包含 95 个 ProcId 的作业簇：

```bash
bash analysis/jobs/run_all.sh
```

每个 ProcId 对应一片晶圆，脚本内部通过 wafer 数组映射到相应的 `config_Bxx_xx.yaml`。标准输出和错误日志写入：

```text
analysis/job_logs/job_0.out
analysis/job_logs/job_0.err
...
```

查询作业：

```bash
hep_q -u
```

## 6. 输出结构

输出目录为：

```text
analysis/results/B33-17/
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

解压后的原始 CSV 保留在 `analysis/unzipped/<wafer_name>/`，结果和解压目录已加入 `.gitignore`。
