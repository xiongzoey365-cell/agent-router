# Task-conditioned Capability Sufficiency

本目录实现 training-free 的 `(Model A, Task X)` 能力充分度实验。默认读取根目录 `测试数据.txt` 中的 25 道题，产物写入 `outputs/task_conditioned_capability_sufficiency_no_answer/`。

核心边界：

- 被测模型只输出最小结构化行为证据，不生成最终答案、完整解法、完整 Chain-of-Thought、自评分或难度判断；
- Evaluator 采用 `Rule first, Judge second`：Judge 只提取规则无法完成的语义事实，不能直接打分；
- 不读取 `expected_answer`、`difficulty_level` 或 `difficulty_rationale`，不以最终答案正确性校验分数；
- 不训练 probe/evaluator；LLM-Judge 轨不读取 Hidden State，Hidden-State 轨不读取 Judge 输出；
- 不可观察维度记为 `null`，不等同于能力不足的 `0`；
- `overall_sufficiency` 是所有非 null 维度的简单平均，`relative_difficulty = 1 - overall_sufficiency`；
- 最低充分度维度（并列时全部保留）是当前 model-task pair 的潜在瓶颈。

文件：

- `common.py`：固定 Schema、提示词、JSON 与 Schema 工具；
- `generate_minimal_evidence.py`：被测模型生成最小行为证据；
- `extract_judge_evidence.py`：独立 Judge 提取结构化语义事实；
- `score_sufficiency.py`：固定规则映射到五档分数并聚合；
- `build_report.py`：导出 LLM-Judge 轨 CSV 和 Markdown 报告；
- `extract_hidden_state_features.py`：在同一证据 token 序列上提取独立 Hidden-State 轨；
- `build_hidden_state_report.py`：导出 Hidden-State 轨 CSV 和 Markdown 报告。

预定执行顺序（当前未执行）：

```bash
CUDA_VISIBLE_DEVICES=<空闲卡> /home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/task_conditioned_capability_sufficiency/generate_minimal_evidence.py \
  --model-path <被测模型路径> --model-name <被测模型名称>

CUDA_VISIBLE_DEVICES=<空闲卡> /home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/task_conditioned_capability_sufficiency/extract_judge_evidence.py \
  --judge-model-path <Judge模型路径> --judge-model-name <Judge模型名称>

/home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/task_conditioned_capability_sufficiency/score_sufficiency.py

/home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/task_conditioned_capability_sufficiency/build_report.py
```

建议 Judge 使用不同于被测模型的模型。默认输出保留一个共享 `model_evidence.json`，并分别写入 `llm_judge/` 与 `hidden_state/`。两轨不共享评分、不融合结果。
