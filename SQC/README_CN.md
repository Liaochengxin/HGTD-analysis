# HGTD Sensor SQC 分析

> English version: [README.md](README.md)

本目录对 LGAD 传感器做 SQC 交叉校验：同一片传感器（15×15 = 225 pad 阵列）的
探针台（Needle，逐 pad）与 15×1 探针卡（ProbeCard，逐列）I-V 数据对比，
由 ROOT 宏 `temp_vbdmin_cross_toIME_v2.C` 完成。

宏的处理流程：

1. Vbd 定义为 I-V 曲线穿过 0.5 µA/pad（针台）或 7.5 µA/通道（探卡，= 15×0.5 µA）
   的点，线性内插求出，并做温度校正 `Vbd(20°C) = Vbd − (T−20)×1.1 V/°C`；
2. 统一在 `0.8×VbdMin` 偏压下内插每个 pad/通道的漏电流；
3. 输出 Vbd 地图、漏电地图、直方图、I-V 叠图和统计表 `crosscheck.csv`
   （合格判据：165 V ≤ Vbd(20°C) ≤ 195 V，即 `Valid` 计数）。

## 1. 数据布局

```text
SQC_sample/                        # 针台（SQC）数据，按测试轮次分两代
├── 1st_batch_SQC/B<批次>/W<晶圆>_P<位置>/SweepVoltage0/1-<pad>.csv   (×225)
└── 2n_batch_SQC/B<批次>/W<晶圆>_P<位置>/SweepVoltage0/1-<pad>.csv   (×225)

CQC_sample/2nd_batch_95/           # 探卡（CQC）数据（由 script/unzip_cqc.py 解压）
└── B<批次>_<晶圆>/<晶圆序列号>/20WS20<批次><晶圆><位置>-<通道>.csv    (每晶圆 780)

test_CQC/                          # 早期手工解压的两个晶圆，作为后备匹配源
CQC_sample/2nd_batch_95/wafer_temperature_template.csv   # 每片晶圆的 CQC 测试温度
```

温度表序列号规则：`20WS0013 + 批次末位 + {晶圆:05d}`，如 `20WS0013100015`
对应 B31 晶圆 15。

## 2. config.yaml

所有全局参数集中在这一个配置里，`main_path` 为绝对路径，其余均为相对
`main_path` 的路径：

```yaml
main_path: /lustrefs/atlas/SUSY/users/liaocx/HGTD/
sqc_folder: SQC_sample                                      # 针台数据根目录
cqc_folder: CQC_sample/2nd_batch_95                         # 探卡真实匹配源
cqc_fallback_folder: test_CQC                               # 探卡后备匹配源
temp_file: CQC_sample/2nd_batch_95/wafer_temperature_template.csv
macro: HGTD-analysis/SQC/temp_vbdmin_cross_toIME_v2.C
output_path: HGTD-analysis/SQC/results
tn: 20.0                                                    # 针台测试温度 (°C)
```

探卡匹配优先级（`find_cqc`）：

1. `cqc_folder` 中按目录名 `B<批次>_<晶圆>` 真实配对，Tp 取温度表中该晶圆
   序列号的精确值；
2. `cqc_fallback_folder` 中按序列号 `20WS2<批次><晶圆><位置>` 精确配对；
3. 以上都找不到时使用任一真实探卡数据占位——占位只影响输出的 ProbeCard
   侧，针台（SQC）结果与它无关。

目前 2nd 批（B31/B33/B36）全部真实配对；1st 批（B06/B07/B15/B18/B21）
尚无对应 CQC 数据，为占位。

## 3. 本机批量运行

```bash
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml --filter B31
python3 HGTD-analysis/SQC/run_all_sqc.py HGTD-analysis/SQC/config.yaml --dry-run
```

自动扫描 `sqc_folder` 下所有 `B*/W*_P*/SweepVoltage0`，逐片调用宏，每片约
2 秒。输出写入 `output_path/<轮次>-B<批次>-W<晶圆>-P<位置>/`，并汇总为
`output_path/summary_all.csv`（每片 4 行：ProbeCard / Needle / inner /
inner2 的 Mean、RMS、VbdMin、IRatio、LKG、Valid）。

## 4. IHEP 集群批量提交

```bash
python3 HGTD-analysis/SQC/make_condor_jobs.py HGTD-analysis/SQC/config.yaml
cd condor && ./submit_all.sh
```

`make_condor_jobs.py` 扫描出全部传感器后生成 `condor/` 包：

```text
condor/
├── sensors.list        # 每行一个传感器：标签|Tp|探卡绝对路径|针台绝对路径
├── job.sh              # $1 = ProcId → sensors.list 对应行 → root 宏
├── submit_all.sh       # 单次 hep_sub job.sh -argu "%{ProcId}" -n N
├── root_env.sh         # 集群 ROOT 加载（按需编辑）
└── collect_results.py  # 结束后合并 results/*/crosscheck.csv → summary_all.csv
```

一次 `hep_sub` 生成一个作业簇（同一 cluster id），N 个传感器 = N 个 ProcId，
一个传感器一个作业并行运行。

注意：生成的作业文件里是**绝对路径**（config 的 `main_path` + 相对路径），
因此 `make_condor_jobs.py` 必须在集群上、数据就位后于最终位置运行一次。
上传数据时排除 zip：`tar czvf target.tar.gz --exclude='*.zip' ...`。

作业管理：

```bash
hep_q -u $USER        # 查询
hep_rm <clusterid>    # 删除整个作业簇
```

## 5. 已知注意事项

- **Tn=20 是假设值**。已测传感器普遍呈现探卡比针台低 ~9–13 V 的系统差
  （如 B31-W15：182 vs 194），会整体把 Vbd 推出 165–195 V 合格窗口、
  令 `Valid` 失真（如 B36 两片 0/225、1/225，实际并无大面积坏点）。
  核实针台真实测试温度后改 config 里的 `tn` 重跑即可；
- `Valid` 是"落在 165–195 V 窗口内的比例"，不等于"好 pad 比例"，
  解读时注意系统偏差的影响；
- 三个针台目录含 226 个文件（多 1 个），宏只读 1–225，无影响；
- `process_perpad.C` / `run.C` 为单列求和的早期工具，尚未接入 config，
  直接 `root -l -b -q run.C` 使用。
