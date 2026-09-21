# Qwen3-8B 单次预推理收敛性实验依据

## 1. 目的

本实验使用一次、有限预算的预推理，观察 Qwen3-8B 是否能快速形成稳定的解题方向。它衡量的是“任务对当前模型造成的预推理负担”，不是题目的绝对难度，也不评价最终答案正确性。

本方案替代“固定截取前 N 个 Token 后计算单 Token 聚类熵”的做法。它不计算生成不确定性或语义熵，不做多次采样，不生成完整答案，也不与 L1–L5 标签比较。

## 2. 实验边界

- 每题只进行一次确定性预推理，`do_sample=False`；
- 最大生成预算为 256 Token；
- 模型可用 `<READY>` 或 `<UNRESOLVED>` 提前结束；
- 只向模型提供 `prompt`，不提供参考答案、难度说明或标签；
- `difficulty_level` 只随结果保存，不能参与指标计算；
- 不输出融合分数，保留各项原始收敛观测；
- 不根据本测试集调阈值。

## 3. 提示词与结束状态

系统提示词为：

```text
你正在进行一次有限预算的预分析，而不是完整作答。请只分析关键约束、候选解题路径和仍未解决的障碍，不要给出完整答案。若解题路径已经明确且不存在关键障碍，请在末尾单独输出 <READY> 并立即停止。若发现题目矛盾、信息不足，或在预算内无法确定可靠路径，请在末尾单独输出 <UNRESOLVED> 并立即停止。不要在其他位置使用这两个标记。
```

应用 Qwen3 官方 Chat Template，并启用 Thinking 模式。程序检测到任一结束标记的完整 Token 序列后立即停止。结果状态定义为：

- `ready`：出现 `<READY>`；
- `unresolved`：出现 `<UNRESOLVED>`；
- `budget_exhausted`：达到 256 Token，未出现标记；
- `ended_without_marker`：模型先输出 EOS，但没有标记。

显式状态是模型自报信号，不代表答案一定正确。

## 4. 窗口级隐藏表示

对实际生成的预推理序列执行一次因果前向传播，读取最后 4 层 Hidden States。对每个生成 Token：

1. 各层向量分别 L2 归一化；
2. 对 4 层求平均并再次归一化；
3. 每连续 32 Token 构成一个窗口，最后不足 32 Token 的部分保留；
4. 对窗口内 Token 向量求平均并归一化，得到窗口表示 `w_i`。

标记 Token 参与“使用 Token 数”统计，但从窗口语义分析中移除。

## 5. 观测指标

### 5.1 收敛长度

`convergence_tokens` 是生成开始至停止的 Token 数。它只在相同模型、提示词和预算下可比较。较长表示模型需要更多预分析，不能单独解释为更难。

### 5.2 末段稳定度

取最后最多 3 个窗口，计算所有两两余弦相似度的平均值：

\[
TerminalStability=mean(\cos(w_i,w_j))
\]

少于 2 个窗口时记为 `null`。高值表示末段语义方向相近，但可能是正常收敛，也可能是重复循环。

### 5.3 语义回访率

对第 3 个及之后的窗口，若它与任一非相邻历史窗口的余弦相似度大于等于 0.95，则视为回访：

\[
SemanticRevisitRate=\frac{回访窗口数}{可检测窗口数}
\]

该指标用于发现“回到先前思路”，不称为语义熵。

### 5.4 词面重复率

对预推理文本按 tokenizer Token ID 构造 4-gram。重复出现的 4-gram 占全部 4-gram 的比例记为 `lexical_repetition_rate`。它辅助区分稳定收敛和机械重复。

### 5.5 路径反转次数

在文本中统计预先固定的中英文修正短语，例如 `wait`、`however`、`actually`、`reconsider`、`not correct`、`等等`、`但是`、`重新考虑`、`前面不对`。结果记为 `path_reversal_count`。这是可解释的词面诊断，不是完整的语义判断。

### 5.6 相邻窗口变化

记录相邻窗口余弦距离的均值 `mean_adjacent_window_distance`，用于描述推理方向变化幅度。它不与其他指标融合。

## 6. 结果解释

优先联合观察，而不是单看某一列：

| 典型表现 | 可能解释 |
| --- | --- |
| `ready`、Token 少、反转少、重复低 | 快速形成稳定路径 |
| `ready`、稳定度高但重复也高 | 可能循环后自报收敛 |
| `unresolved` | 模型主动识别关键障碍或题目问题 |
| `budget_exhausted`、反转高 | 路径持续摇摆 |
| `budget_exhausted`、重复高 | 预推理循环 |
| Token 少但稳定度为 `null` | 信息不足，不能据此判断内部稳定性 |

快速收敛可能收敛到错误路径；不收敛也可能源于题目矛盾、歧义或模型行为，而非计算难度。因此，本阶段只记录分布，不评价方法与 L1–L5 的一致性。

## 7. 输出

默认目录为 `outputs/single_pass_convergence/`，包含：

- `results.json`：实验配置与逐题完整结果；
- `results.csv`：便于统计的扁平结果；
- `report.md`：按结束状态和任务类型汇总，并列出逐题观测。

脚本必须记录模型、设备、精度、依赖版本、窗口大小、阈值、最大预算和随机种子。单题异常不得中断其余任务。

## 8. 默认执行方式

```bash
CUDA_VISIBLE_DEVICES=<空闲卡> \
/home/xiongziyan/anaconda3/envs/vllm/bin/python single_pass_convergence_probe.py \
  --model-path <Qwen3-8B本地路径> \
  --input-file 测试数据.txt \
  --output-dir outputs/single_pass_convergence \
  --trust-remote-code
```

脚本基于 Transformers 执行，因为实验需要读取生成 Token 的 Hidden States。执行前必须先用 `nvidia-smi` 选择空闲显卡。
