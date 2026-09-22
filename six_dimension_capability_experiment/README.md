# 六维能力输出与无提示基线实验

本目录包含两个相互独立的 Qwen3-8B 推理分支：

- `six_dimension`：统一使用六维 system prompt，只输出六个维度下应如何处理题目，不继续生成最终答案。
- `no_prompt_baseline`：只向聊天模板提供测试数据中的原始 user 题目，不添加 system prompt、六维提示、参考答案或其他辅助内容，直接作答。

两个分支均关闭 Qwen3 显式 thinking 模式，使用相同的贪心解码设置。六维分支不会作为基线分支的输入，两者不存在“先规划再回答”的上下文污染。

## 运行

```bash
CUDA_VISIBLE_DEVICES=2 \
/home/xiongziyan/anaconda3/envs/agent-router-qwen/bin/python \
  run_experiment.py \
  --device cuda:0
```

脚本支持断点续跑；已有的逐题文本、记录和隐藏状态文件同时存在时会跳过。使用 `--overwrite` 可显式覆盖。

只运行部分题目进行检查：

```bash
CUDA_VISIBLE_DEVICES=2 \
/home/xiongziyan/anaconda3/envs/agent-router-qwen/bin/python \
  run_experiment.py \
  --device cuda:0 \
  --task-ids code_L1_001
```

## 输出结构

```text
outputs/
├── manifest.json
├── input_snapshot.json
├── completion.json
├── six_dimension/
│   ├── system_prompt.txt
│   ├── prompt_policy.txt
│   ├── all_outputs.jsonl
│   ├── all_outputs.md
│   ├── records/*.json
│   ├── raw_text/*.txt
│   └── raw_hidden_states/*.pt
└── no_prompt_baseline/
    ├── prompt_policy.txt
    ├── all_outputs.jsonl
    ├── all_outputs.md
    ├── records/*.json
    ├── raw_text/*.txt
    └── raw_hidden_states/*.pt
```

每个 `records/*.json` 保存原题、实际 message 列表、渲染后的完整模型输入、输入/输出 token ID、原始输出、终止原因和隐藏状态元数据。

每个 `raw_hidden_states/*.pt` 保存：

- 渲染后的提示词和全部生成 token 对应的 `input_ids`；
- `attention_mask`；
- embedding 输出、所有 decoder 深度状态和最终归一化输出；
- 原始 tensor 形状与 dtype。

隐藏状态不做池化、切片、归一化、量化、特征提取或 dtype 转换，只执行 `detach` 和无损 CPU 搬移后用 `torch.save` 序列化。

## 复现说明

- 模型：本机缓存的 `Qwen3-8B` 固定 snapshot。
- 解码：`do_sample=False`，固定 seed 42。
- thinking：两个分支均为 `enable_thinking=False`，避免把隐藏思考文本混入实验差异。
- 默认输出上限：六维分支 2048 token；基线分支 4096 token。
- 输入快照和原始数据文件 SHA-256 会写入 `manifest.json`。
