# 第一阶段：无训练、通用输出证据

本目录实现“一次结构化预推理 + 通用规则特征”的第一阶段方法。

核心边界：

- 所有任务使用同一提示词和同一套特征，不编写逐任务规则；
- Qwen3-8B只输出执行前分析，不输出答案、能力分、信心或难度；
- 不训练分析器，不读取Hidden State，不进行多次采样；
- 不判断领域答案是否正确；
- 不把六维特征融合成总分；
- L1-L5只保留用于可选的结果分组，不参与任何指标计算。

文件：

- `第一阶段_无训练通用输出证据实验依据.md`：正式实验定义；
- `generic_common.py`：共享提示词、解析和无训练字面对齐工具；
- `run_prereason.py`：执行一次确定性结构化预推理；
- `extract_generic_features.py`：提取六个维度的通用原始证据；
- `build_report.py`：生成CSV与Markdown分布报告。

预定执行顺序：

```bash
CUDA_VISIBLE_DEVICES=<空闲卡> \
/home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/phase1_no_training_output_evidence/run_prereason.py \
  --model-path /home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218

/home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/phase1_no_training_output_evidence/extract_generic_features.py

/home/xiongziyan/anaconda3/envs/vllm/bin/python \
  new_method/phase1_no_training_output_evidence/build_report.py
```

默认输出目录：

`outputs/phase1_no_training_output_evidence/`

当前提交只完成代码与依据，不执行上述命令。
