# 实验结果与完整性检查

## 运行结果

- 模型：Qwen3-8B，本机固定 Hugging Face snapshot。
- 测试题：25 道。
- 六维输出分支：25 份文本、25 份 JSON 记录、25 份原始隐藏状态。
- 无提示基线分支：25 份文本、25 份 JSON 记录、25 份原始隐藏状态。
- 隐藏状态总量：约 11 GB。
- 两个分支均使用贪心解码、`enable_thinking=False` 和 seed 42。

## 独立性检查

- 六维分支的 25 条输入均为 `system + user`，其中 system 是同一个六维提示词，user 是原始题目。
- 无提示基线的 25 条输入均只有 `user`，内容是原始题目；没有 system 消息、六维提示、六维输出、参考答案或其他辅助提示。
- 两个分支分别从各自消息构造模型输入，六维输出没有被传给基线分支。

## 隐藏状态检查

- 每个样本保存 37 个 `torch.bfloat16` tensor。
- 每个 tensor 保留 batch、完整 token 序列和 4096 维隐藏向量。
- token 序列覆盖渲染后的完整提示和全部生成 token。
- 每份隐藏状态的序列长度均等于记录中的 `prompt_tokens + generated_tokens`。
- 未进行池化、token 切片、归一化、量化、特征提取或 dtype 转换。
- 每个 `.pt` 的 SHA-256、字节数、tensor 标签、形状和 dtype 已写入对应逐题 JSON 记录。

## 终止情况

- 六维分支：25/25 均由 EOS 正常终止，生成长度范围为 62–808 token。
- 无提示基线：24/25 由 EOS 正常终止。
- `logic_L3_018` 的无提示回答达到 4096-token 安全上限。该题的约束本身不可满足，模型在排列搜索中反复尝试；脚本完整保留了上限前的所有输出 token、终止原因和对应隐藏状态。

## 六维格式的可观察结果

- 23/25 个六维分支输出包含全部六个维度标签。
- `inst_L4_024` 和 `inst_L5_025` 没有按 system prompt 输出六维内容，而是直接执行了原题中的严格格式要求。
- 上述两个偏离样本保持原样，没有重跑、人工修复或筛除。它们可作为模型在高强度用户约束下发生 system 指令偏离的直接观察证据。
- 14 个六维输出至少一次明确使用“没有明显体现”“未体现”或“不适用”等表述，其余输出由模型自行认为六个维度均有可说明内容；实验未强制事后修正。

## 目录入口

- 实验实现：`run_experiment.py`
- 运行和数据格式说明：`README.md`
- 完整运行配置：`outputs/manifest.json`
- 输入数据快照：`outputs/input_snapshot.json`
- 完成计数：`outputs/completion.json`
- 六维输出汇总：`outputs/six_dimension/all_outputs.md`
- 无提示回答汇总：`outputs/no_prompt_baseline/all_outputs.md`
- 逐题完整记录：两个分支各自的 `records/`
- 逐题原始文本：两个分支各自的 `raw_text/`
- 逐题原始隐藏状态：两个分支各自的 `raw_hidden_states/`
