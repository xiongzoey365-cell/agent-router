# Qwen3-8B 想法一与想法三实验实现依据

## 1. 文档目的

本文档是当前阶段实现与执行的唯一依据。目标是在不评价完整答案、不使用测试集 L1–L5 标签校准结果、也不融合两种方法的前提下，对 `测试数据.txt` 中的 25 道题分别运行：

1. 想法一：隐空间语义熵与轨迹漂移探测；
2. 想法三：Prefill 阶段注意力拓扑分析。

每种方法为每道题输出一个 0–100 的独立探针指标，并保留构成该指标的原始诊断值。当前指标只能解释为该方法观测到的“内部认知负荷”，不能解释为已经验证过的真实难度。

## 2. 实验边界

本阶段必须遵守以下边界：

- 不生成或评价完整答案；
- 不使用 `expected_answer`、`difficulty_rationale` 或 `agent_mapping` 作为模型输入；
- 保留 `difficulty_level` 方便追溯数据，但不用于指标计算、参数训练或结果比较；
- 想法一和想法三分开实现、分开执行、分开保存结果；
- 不计算两种方法的融合分数；
- 不根据 25 道题的 L1–L5 标签调整公式或权重；
- 本阶段只运行一次确定性探测，不做多次采样。

## 3. 输入数据

输入文件默认为 `测试数据.txt`。文件内容是 JSON，顶层必须包含 `tasks` 数组。每条任务至少包含：

- `task_id`
- `task_type`
- `difficulty_level`
- `prompt`

真正发送给模型的任务内容只能来自 `prompt`。

## 4. 统一模型配置

两个脚本使用相同的基础配置：

| 配置项 | 默认要求 |
| --- | --- |
| 模型 | Qwen3-8B，由命令行提供本地路径或 Hugging Face 模型名 |
| 推理模式 | `model.eval()` 与 `torch.inference_mode()` |
| 权重精度 | BF16；硬件不支持时由执行者显式改为 FP16/FP32 |
| 量化 | 不量化 |
| Batch size | 1 |
| Chat Template | 模型官方 Chat Template |
| 采样 | 关闭，`do_sample=False` |
| 随机种子 | 42 |

实验结果必须记录模型路径、精度、设备、Transformers 版本、PyTorch 版本和脚本参数。

## 5. 想法一：隐空间语义熵与轨迹漂移

### 5.1 探针输入和生成

每道题构造成两条消息：

```text
system: 请开始分析下面问题的解决思路，不要直接给出最终答案。
user: {prompt}
```

使用 Qwen3 Thinking 模式，确定性生成恰好 20 个新 Token：

```text
max_new_tokens = 20
min_new_tokens = 20
do_sample = false
```

保存这 20 个 Token 解码后的 `probe_text`，但不继续生成完整答案。

### 5.2 Hidden State 提取

生成完成后，将“输入 Token + 20 个生成 Token”做一次因果前向传播并返回 Hidden States。由于因果掩码保证某一位置不受其后 Token 影响，这与逐 Token 解码时提取相同位置表示在语义上等价，同时实现更稳定。

只保留最后 4 个 Transformer 层、最后 20 个生成位置的 Hidden State。对每个生成位置：

1. 分别对 4 层向量做 L2 归一化；
2. 对 4 层取平均；
3. 对平均向量再次做 L2 归一化。

每道题最终得到轨迹：

\[
h_1,h_2,\ldots,h_{20}
\]

### 5.3 归一化语义熵

完成全部任务的 Hidden State 采集后，将所有成功样本汇总。默认共有 25 × 20 = 500 个向量。

1. 使用同一个 PCA 将向量降至最多 64 维；
2. 使用同一个 KMeans 将向量划分为 8 个簇；
3. 对每道题统计 20 个状态落入各簇的比例 `p(c)`；
4. 计算归一化语义熵。

\[
H=-\sum_{c=1}^{K}p(c)\log p(c)
\]

\[
H_{norm}=\frac{H}{\log K}
\]

其中 `K=8`，因此 `H_norm` 位于 `[0,1]`。PCA 和 KMeans 只能在整个批次上统一拟合一次，不能为每道题单独拟合。

### 5.4 归一化轨迹漂移

相邻状态距离：

\[
S=\frac{1}{19}\sum_{t=2}^{20}\frac{1-\cos(h_t,h_{t-1})}{2}
\]

方向变化：

\[
\Delta_t=h_t-h_{t-1}
\]

\[
T=\frac{1}{18}\sum_{t=3}^{20}\frac{1-\cos(\Delta_t,\Delta_{t-1})}{2}
\]

归一化轨迹漂移：

\[
D_{norm}=\frac{S+T}{2}
\]

`S`、`T` 和 `D_norm` 均限制在 `[0,1]`。

### 5.5 想法一主指标

每道题唯一的主指标为：

\[
LatentLoadScore=100\times\frac{H_{norm}+D_{norm}}{2}
\]

分数越高，只表示想法一观测到的隐空间负荷越高。`semantic_entropy_normalized`、`mean_step_distance`、`direction_change` 和 `trajectory_drift_normalized` 作为解释字段保存。

## 6. 想法三：Prefill 注意力拓扑

### 6.1 输入和 Prefill

只使用一条用户消息：

```text
user: {prompt}
```

应用官方 Chat Template 后只执行一次 Prefill，不生成新 Token。模型必须使用能够返回完整注意力矩阵的 eager attention：

```text
output_attentions = true
use_cache = false
attn_implementation = "eager"
```

只读取最后 2 个 Transformer 层的 Attention Matrix。

### 6.2 用户 Token 范围

Chat Template 中可能包含固定模板和特殊 Token。实现必须通过 fast tokenizer 的字符 offset 找到原始 `prompt` 对应的 Token，只分析用户问题内部的 Query 和 Key，并在切片后对注意力重新归一化。

不分析 System、Chat Template、Assistant 起始标记或 Padding Token。

### 6.3 归一化注意力熵

对最后 2 层、每个 Head、每个用户 Query Token，在其能够关注的用户 Key Token 上计算：

\[
H_i=-\sum_j a_{ij}\log a_{ij}
\]

\[
E_i=\frac{H_i}{\log N_i}
\]

`N_i` 是当前 Query 可以关注的有效用户 Key 数。`N_i=1` 的行没有可比较分布，跳过。对有效 Token、Head 和层取平均得到：

\[
E_{attention}\in[0,1]
\]

### 6.4 关键节点集中度

对每个有效注意力分布，选择权重最高的前 10% Key Token，至少选择 1 个，计算其注意力质量之和：

\[
C_i=\sum_{j\in Top10\%}a_{ij}
\]

对有效 Token、Head 和层取平均得到：

\[
C_{attention}\in[0,1]
\]

值越高表示注意力越集中，故负荷方向使用 `1-C_attention`。

### 6.5 想法三主指标

每道题唯一的主指标为：

\[
AttentionLoadScore=100\times\frac{E_{attention}+(1-C_{attention})}{2}
\]

分数越高，只表示想法三观测到的注意力负荷越高。

### 6.6 拓扑诊断字段

将最后 2 层和所有 Head 的用户 Token 注意力取平均，得到聚合矩阵。排除自环后，将权重大于 0.1 的因果连接视为边，记录：

- `graph_density_threshold_01`：实际边数除以因果掩码下可能存在的最大非自环边数；
- `cycle_count`：记录为 0。因果注意力只允许当前位置关注此前位置，排除自环后必然是有向无环图。

这两个字段不进入 `AttentionLoadScore`。固定阈值图密度只用于忠实记录原始方案中的拓扑观察，不能单独解释为难度。

## 7. 两种方法的独立输出

想法一默认输出到 `outputs/method1_latent/`：

- `results.json`
- `results.csv`
- `report.md`
- `scores_bar.png`
- `scores_histogram.png`

想法三默认输出到 `outputs/method3_attention/`，文件名相同。

两个目录之间没有共享结果文件，不产生联合分数。

### 7.1 想法一 CSV 字段

```text
task_id,task_type,difficulty_level,probe_text,
semantic_entropy_raw,semantic_entropy_normalized,
mean_step_distance,direction_change,trajectory_drift_normalized,
latent_load_score,runtime_ms,peak_memory_mb,status,error
```

### 7.2 想法三 CSV 字段

```text
task_id,task_type,difficulty_level,prompt_tokens,user_tokens,
attention_entropy_normalized,top10_attention_concentration,
graph_density_threshold_01,cycle_count,
attention_load_score,runtime_ms,peak_memory_mb,status,error
```

## 8. 结果报告

每个方法的 `report.md` 独立报告：

- 实验配置；
- 成功和失败数量；
- 主指标的最小值、最大值、平均值和中位数；
- 25 道题的逐题结果；
- 异常或失败原因；
- 平均运行时间和峰值显存。

图表只展示该方法自己的 25 道题柱状图和分数直方图。不按 L1–L5 聚合，不计算相关性，不评价哪个方法更准确。

## 9. 技术验收条件

执行后必须满足：

1. 每个脚本都读取到 25 条任务；
2. 每个成功样本的主指标位于 `[0,100]`；
3. 结果中不存在未处理的 NaN 或 Inf；
4. 想法一每个成功样本包含 20 个生成 Token 的状态；
5. 想法三只统计原始用户问题对应的 Token；
6. 两个脚本可以分别执行，不要求另一个脚本或另一个结果目录存在；
7. 任一单题失败时记录 `status=error` 和错误信息，并继续处理其他任务；
8. 不生成完整答案，不做 L1–L5 比较，不产生融合结果。

## 10. 独立执行命令

想法一：

```bash
python method1_latent_probe.py \
  --model-path /path/to/Qwen3-8B \
  --input-file 测试数据.txt \
  --output-dir outputs/method1_latent
```

想法三：

```bash
python method3_attention_probe.py \
  --model-path /path/to/Qwen3-8B \
  --input-file 测试数据.txt \
  --output-dir outputs/method3_attention
```

本文件冻结当前阶段的指标定义。后续如需加入 L1–L5 比较、完整答案质量评价、参数校准或多方法融合，应另建实验阶段，不得无记录地修改本阶段结果含义。

## 11. 想法一第二轮补充实验：Token 20:40

第一轮结果显示前 20 个生成 Token 高度集中于通用分析开场。第二轮保持其余公式、模型、精度、PCA、聚类数和轨迹指标不变，只调整采集区间：每题确定性生成 40 个新 Token，丢弃前 20 个，仅分析生成序列末尾 20 个（即 0-based 区间 20:40）。结果保存到 `outputs/method1_latent_tokens_20_40/`，不得覆盖第一轮。

```bash
python method1_latent_probe.py \
  --model-path /path/to/Qwen3-8B \
  --input-file 测试数据.txt \
  --output-dir outputs/method1_latent_tokens_20_40 \
  --new-tokens 40 \
  --analysis-tokens 20
```

## 12. 想法一第三轮补充实验：Token 40:60

第三轮保持其余公式、模型、精度、PCA、聚类数和轨迹指标不变。每题确定性生成 60 个新 Token，丢弃前 40 个，仅分析生成序列末尾 20 个（即 0-based 区间 40:60）。结果保存到 `outputs/method1_latent_tokens_40_60/`，不得覆盖前两轮。

```bash
python method1_latent_probe.py \
  --model-path /path/to/Qwen3-8B \
  --input-file 测试数据.txt \
  --output-dir outputs/method1_latent_tokens_40_60 \
  --new-tokens 60 \
  --analysis-tokens 20
```

## 13. 想法一第四轮补充实验：累计 Token 0:60

第四轮保持其余公式、模型、精度、PCA、聚类数和轨迹指标不变。每题确定性生成 60 个新 Token，并分析全部 60 个 Hidden State。全体 25 道题共 1500 个状态，共用同一套 PCA 和 KMeans。结果保存到 `outputs/method1_latent_tokens_0_60/`。该结果表示前 60 Token 的整体负荷，不单独表示窗口收敛趋势。

```bash
python method1_latent_probe.py \
  --model-path /path/to/Qwen3-8B \
  --input-file 测试数据.txt \
  --output-dir outputs/method1_latent_tokens_0_60 \
  --new-tokens 60 \
  --analysis-tokens 60
```
