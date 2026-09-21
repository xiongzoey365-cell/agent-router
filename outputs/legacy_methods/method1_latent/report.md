# 想法一实验结果

> 本报告只展示隐空间探针结果，不评价完整答案，也不与 L1–L5 比较。

## 实验配置

- 模型：`/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- 设备：`cuda`
- 精度：`bf16`
- 生成 Token：20
- 最后层数：4
- PCA 维度：64
- 聚类数：8
- 成功/总数：25/25

## 汇总

- 最小分数：45.5253
- 最大分数：64.0552
- 平均分数：55.6268
- 中位数：55.9029
- 平均耗时：807.34 ms
- 最大峰值显存：15817.54 MB

## 逐题结果

| task_id | task_type | 语义熵 | 轨迹漂移 | LatentLoadScore | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| code_L1_001 | code_generation | 0.6570 | 0.4275 | 54.2260 | success |
| code_L2_002 | code_generation | 0.6055 | 0.4249 | 51.5229 | success |
| code_L3_003 | code_generation | 0.6903 | 0.4277 | 55.9029 | success |
| code_L4_004 | code_generation | 0.6570 | 0.4255 | 54.1240 | success |
| code_L5_005 | code_generation | 0.6055 | 0.4182 | 51.1855 | success |
| math_L1_006 | math_reasoning | 0.7537 | 0.4332 | 59.3412 | success |
| math_L2_007 | math_reasoning | 0.7383 | 0.4071 | 57.2736 | success |
| math_L3_008 | math_reasoning | 0.6938 | 0.4165 | 55.5170 | success |
| math_L4_009 | math_reasoning | 0.8761 | 0.4050 | 64.0552 | success |
| math_L5_010 | math_reasoning | 0.7488 | 0.4198 | 58.4320 | success |
| qa_L1_011 | knowledge_qa | 0.6733 | 0.4098 | 54.1573 | success |
| qa_L2_012 | knowledge_qa | 0.7383 | 0.4040 | 57.1188 | success |
| qa_L3_013 | knowledge_qa | 0.8220 | 0.4032 | 61.2601 | success |
| qa_L4_014 | knowledge_qa | 0.7203 | 0.4250 | 57.2653 | success |
| qa_L5_015 | knowledge_qa | 0.6055 | 0.4134 | 50.9478 | success |
| logic_L1_016 | logical_reasoning | 0.7203 | 0.4288 | 57.4576 | success |
| logic_L2_017 | logical_reasoning | 0.7880 | 0.4029 | 59.5415 | success |
| logic_L3_018 | logical_reasoning | 0.7526 | 0.4004 | 57.6466 | success |
| logic_L4_019 | logical_reasoning | 0.6744 | 0.4296 | 55.1983 | success |
| logic_L5_020 | logical_reasoning | 0.5189 | 0.3916 | 45.5253 | success |
| inst_L1_021 | instruction_following | 0.7863 | 0.4281 | 60.7203 | success |
| inst_L2_022 | instruction_following | 0.6397 | 0.4055 | 52.2610 | success |
| inst_L3_023 | instruction_following | 0.6376 | 0.3969 | 51.7246 | success |
| inst_L4_024 | instruction_following | 0.5903 | 0.4160 | 50.3144 | success |
| inst_L5_025 | instruction_following | 0.7488 | 0.4102 | 57.9518 | success |
