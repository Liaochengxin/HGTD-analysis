# 当前 results 后处理审核

审核日期：2026-10-11。范围为 HGTD-analysis 的 Python 提取、良率汇总、SQC 汇总和绘图入口。
CERN 路径基准仍为 `/eos/user/l/liaoc/public/HGTD_sensor`；原有 ROOT 宏的计算定义未修改。
以下命令从该目录执行。CQC 良率收集、比较和良率 summary 的相对路径继续按该 CERN 基准解析；
原先按工作目录解析的绘图和提取入口保留其调用方式。所有入口均可传显式绝对路径。

## 当前数据结构

```text
CQC_results/
  CERN/1nd_batch_100_IHEP/B15_11/{sensorYield.csv,B15_11.root,run.log,...}
  CERN/2nd_batch_95_IHEP/B31_10/{sensorYield.csv,B31_10.root,run.log,...}
  CERN/pilot_batch_17_IHEP/B04_2/{sensorYield.csv,B04_2.root,run.log,...}
  IHEP/3nd_batch_25_IME/B34_10/sensorYields.csv
SQC_results/
  CERN/1nd_batch/sensor_plan.csv
  CERN/1nd_batch/B06/W01-P2/{crosscheck.csv,W01-P2.root,run.log,...}
  CERN/2nd_batch/sensor_plan.csv
  CERN/2nd_batch/B31/W04-P1/{crosscheck.csv,W04-P1.root,run.log,...}
```

- CQC `ChannelResults`：`sensor_id`、`channel_id`、`vbd_at_test_temperature_V`、`vbd_corrected_20C_V`、`leakage_current_A`。
- SQC `SQC_results`：225 个逐像素 `pad_position`、`vbd_corrected_20C_V`、`leakage_current_A`。
- 同一 SQC 文件内的 `CQC_results`：15 个匹配探卡 `channel_id`、`vbd_corrected_20C_V`、`leakage_current_A`。
- Vbd 单位为 V，漏电流单位为 A；ROOT 的 corrected 分支已经修正至 20°C。
- `crosscheck.csv` 的 `RMS/Mean` 是带 `%` 的百分比字符串；`Valid` 是 165–195 V 内的数量。

## 发现与修复

1. **提取依赖日志且损失精度。** 原 CQC 提取读取 `run.log` 中的打印值；当前 ROOT 已保存完整精度。提取默认使用 ROOT，不再重新拟合或重复温度修正。日志模式仍通过 `--input-format log` 显式选择。
2. **SQC 两种 Vbd 定义容易混淆。** 当前 ROOT 的 225 个逐像素 Vbd 不等于把每列 15 个像素的电流求和后求 7.5 µA 交点。ROOT 导出分别使用 `pixel_vbd.csv` 和 `matched_cqc_channels.csv`；旧求和算法通过 `--input-format raw` 保留，仍输出 15 行 `pad_vbd.csv`。旧 `fit_vbd_residual.py` 使用这一求和定义；当前逐像素/列统计残差使用 `plot_sqc_cqc_vbd_residuals.py`。
3. **良率脚本的命名、身份和 schema 校验不足。** 统一解析 `Bxx_wafer`/`Bxx-wafer`，支持两个 yield 文件名及历史 serial 文件名，重复身份或多个候选表明确报错。第二批 vendor 有 4 个晶圆只有 `Sensor,Final_Status`；收集、状态对比使用列并集，缺失物理指标保持为空。
4. **未知状态被归入 B。** 现在仅 B/B1/B2 合并为 B，未知状态报错；原 `Final_Status` 值保留。
5. **良率对比会漏掉缺失身份。** 现在要求两侧 wafer/sensor 集合一致，并校验 CSV 重复 Sensor；summary 同样拒绝重复身份和不一致集合。
6. **SQC collector 指向旧目录，且缺少身份和 Tn。** 新增 `SQC/collect_results.py`，支持 batch、site 或 results root，按各批次 manifest 关联并保留 `Tp/Tn/cqc`，增加 `batch/output_group/output_sensor`。未完成的计划 sensor 会列出；未列入计划或重复身份报错。local runner 和 job generator 共用这一实现，生成脚本仍为独立的标准库脚本。
7. **残差读取的重复 ID 校验被筛选掩盖。** 之前重复 channel 的第一条值不在接受区间时可能逃过检查。现在先记录全部身份，再筛选；浮点 ID 也不再被静默截断为整数。
8. **绘图默认目录和文档过时。** 修复 grade map、delta check、旧求和残差的默认路径；README 移除不存在的 `plot_vbd_avg_rms.py` 入口，使用现有 `CQC/plot_vbd.py` 和 `SQC/plot_vbd.py`。

## 当前结果的调用方式

### ROOT 导出

```bash
python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py \
  --source CQC CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py \
  --source SQC SQC_results/CERN/2nd_batch
```

默认 CSV 写在对应 ROOT 文件旁。`--output-dir` 可以导出到另一目录，并保留输入目录以下的层级。
CQC 的 `probe_card_channels.csv` 保留已有列：
`sensor_location,channel,sensor_class,vbd_20C_V,leakage_current_A`。
SQC 的两个新 CSV 保留原始 ROOT 分支名。

旧输入模式：

```bash
python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py \
  --source CQC --input-format log CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/scirpt/extract_sensor_vbd_results.py \
  --source SQC --input-format raw SQC_sample/2nd_batch_SQC
```

### 良率收集和对比

```bash
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  CQC_results/CERN/2nd_batch_95_IHEP --sample CQC_sample/CERN/2nd_batch_95
python3 HGTD-analysis/CQC/collect_sensor_yields.py \
  CQC_sample/CERN/2nd_batch_95 --label IME --output CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/scirpt/summarize_sensor_yields.py CQC_results/CERN/2nd_batch_95_IHEP
python3 HGTD-analysis/CQC/compare_sensor_yields.py \
  CQC_results/CERN/2nd_batch_95_IHEP --ime CQC_sample/CERN/2nd_batch_95
```

### SQC 汇总和当前 ROOT 残差

```bash
python3 HGTD-analysis/SQC/collect_results.py SQC_results/CERN/1nd_batch
python3 HGTD-analysis/SQC/collect_results.py SQC_results/CERN \
  --output SQC_results/CERN/summary_all.csv
python3 HGTD-analysis/scirpt/plot_sqc_cqc_vbd_residuals.py \
  -i SQC_results/CERN/1nd_batch SQC_results/CERN/2nd_batch \
  --level sensor-level --output SQC_results/CERN/residual_combine
python3 HGTD-analysis/scirpt/plot_sqc_cqc_vbd_residuals.py \
  -i SQC_results/CERN/1nd_batch SQC_results/CERN/2nd_batch \
  --level channel-level --output SQC_results/CERN/residual_combine
```

`SQC/jobs_1nd/collect_results.py` 和 `jobs_2nd/collect_results.py` 的默认路径保持为 CERN EOS，
分别选择当前 `SQC_results/CERN/1nd_batch` 和 `SQC_results/CERN/2nd_batch`。
重新生成 job 时，collector 默认路径遵从 config 的 `output_path`；现有 config 中的旧运行输出路径未修改。
如果运行结果后来迁移到了当前树，显式传入新结果目录即可。

## 验证结果

验证输出写入临时目录，没有覆盖现有 results 或 sample 数据。

| 当前 CQC 批次 | wafer 数 | sensor 行数 | A | B/B1/B2 | C |
|---|---:|---:|---:|---:|---:|
| CERN/1nd_batch_100_IHEP | 100 | 5200 | 3043 | 247 | 1910 |
| CERN/2nd_batch_95_IHEP | 95 | 4940 | 3182 | 90 | 1668 |
| CERN/pilot_batch_17_IHEP | 17 | 884 | 358 | 252 | 274 |
| IHEP/3nd_batch_25_IME | 25 | 1300 | 741 | 251 | 308 |

第二批与 pilot 的完整良率收集、IME 收集、summary 和差异表均验证通过；
两侧最终状态不同的 sensor 分别为 34 和 98 个。
第一批当前 sample 未提供逐晶圆 vendor yield 表，因此仅验证其分析结果收集。

- 212 个 CQC ROOT 文件、70 个 SQC ROOT 文件完成导出；导出 Vbd 和漏电流逐项读取回 CSV，与 ROOT 做浮点精确相等校验。
- SQC 汇总为 70 个 sensor、280 行，缺少计划结果的 sensor 数为 0。
- 沿用 165–195 V 接受区间后，sensor-level 残差包含 56 个 sensor；channel-level 包含 55 个 sensor 的 670 个 channel。
  14 个 sensor 无满足区间的 SQC/CQC 样本，由脚本明确输出 skip；另一个 sensor 没有同列的有效 channel 配对。
- CQC sensor/channel、SQC sensor/pad、两级残差拟合、grade map 和 delta check 共 8 个绘图入口均运行成功。
- 14 个回归测试覆盖 CERN 路径、表格式、重复/缺失身份、仅状态 vendor 表、精度保留、SQC 双树、筛选前重复 channel 和 ID 整数校验。

运行回归测试：

```bash
HGTD-analysis/.venv/bin/python -m unittest discover -s HGTD-analysis/tests -v
```

## 仍需按分析定义解读的事项

- 旧 flat ROOT 输出（`1st_50_*`、`2nd_50_pre`、`pilot_batch` 等）没有当前 `ChannelResults` TTree，不属于本次新结构；不能用当前通道导出/绘图入口读取。
- CQC ROOT 中有 47 个负的 corrected Vbd。导出保留这些原值；没有增加接受区间筛选或把数值替换为零。CQC 通道分布默认也包含全部保存值，需要在分析上区分未找到阈值交点等状态。
- 当前残差的 165–195 V 区间会改变进入拟合的样本集合；本次保留原选择和拟合方法。逐列最小/平均像素 Vbd 与“求和电流的 Vbd”是不同物理定义。
- 本次验证的是本地同步的实际结果和脚本入口，没有在 CERN worker 上重新提交 ROOT 生产任务。
