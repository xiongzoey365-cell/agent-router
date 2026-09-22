# 单段工作便笺能力探测

本目录使用固定的通用提示词，让本地 Qwen3-8B 针对 `测试数据.txt` 中的每道题只生成一段“执行前工作便笺”，不输出最终答案。同时保存生成文本、token ID，以及完整输入序列上未经聚合或特征化的原始隐藏状态。

## 运行

在仓库根目录执行：

```bash
python single_paragraph_capability_probe/run_probe.py
```

默认模型为本机已有的 Qwen3-8B snapshot。可显式指定模型和 GPU：

```bash
python single_paragraph_capability_probe/run_probe.py \
  --model-path /path/to/Qwen3-8B \
  --device cuda:0 \
  --output-dir single_paragraph_capability_probe/outputs
```

程序默认跳过已经完整生成的题目，可安全续跑。若需要覆盖已有结果，增加 `--overwrite`。

## 输出

所有结果都位于本目录下的 `outputs/`：

- `manifest.json`：模型、提示词、运行环境和隐藏状态采集方式；
- `system_prompt.txt`：实验使用的完整固定提示词；
- `all_outputs.jsonl`：所有已完成题目的汇总记录；
- `records/<task_id>.json`：单题输入、原始输出、token ID和文件索引；
- `raw_text/<task_id>.txt`：模型生成的原始文本；
- `raw_hidden_states/<task_id>.pt`：PyTorch 原始张量文件。

每个 `.pt` 文件包含完整 `input_ids`、`attention_mask` 和 `hidden_states` 元组。`hidden_states[0]` 是 embedding 输出，后续元素是每个 Transformer 层的输出，保留 `[batch, sequence, hidden]` 形状与模型原始 dtype。保存前只执行 `detach()` 和无损 CPU 设备迁移，不进行切片、池化、归一化、量化、降维或 dtype 转换。

载入示例：

```python
import torch

artifact = torch.load(
    "single_paragraph_capability_probe/outputs/raw_hidden_states/code_L1_001.pt",
    map_location="cpu",
    weights_only=False,
)
print(len(artifact["hidden_states"]))
print(artifact["hidden_states"][0].shape, artifact["hidden_states"][0].dtype)
```

## 依赖

沿用仓库根目录 `requirements-experiment.txt` 中的 PyTorch、Transformers 和 NumPy 版本。
