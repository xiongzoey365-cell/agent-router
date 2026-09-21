# 想法一实验结果

> 本报告只展示隐空间探针结果，不评价完整答案，也不与 L1–L5 比较。

## 实验配置

- 模型：`/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- 设备：`cuda`
- 精度：`bf16`
- 生成 Token：60
- 分析 Token：生成序列末尾 60 个
- 最后层数：4
- PCA 维度：64
- 聚类数：8
- 成功/总数：25/25

## 汇总

- 最小分数：45.4410
- 最大分数：65.0378
- 平均分数：58.6078
- 中位数：58.8037
- 平均耗时：2917.49 ms
- 最大峰值显存：15850.15 MB

## 逐题结果

| task_id | task_type | 语义熵 | 轨迹漂移 | LatentLoadScore | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| code_L1_001 | code_generation | 0.6443 | 0.4241 | 53.4185 | success |
| code_L2_002 | code_generation | 0.6740 | 0.4299 | 55.1960 | success |
| code_L3_003 | code_generation | 0.6241 | 0.4455 | 53.4804 | success |
| code_L4_004 | code_generation | 0.8226 | 0.4284 | 62.5529 | success |
| code_L5_005 | code_generation | 0.8077 | 0.3994 | 60.3555 | success |
| math_L1_006 | math_reasoning | 0.7591 | 0.4170 | 58.8037 | success |
| math_L2_007 | math_reasoning | 0.7415 | 0.4049 | 57.3191 | success |
| math_L3_008 | math_reasoning | 0.7075 | 0.4224 | 56.4941 | success |
| math_L4_009 | math_reasoning | 0.8726 | 0.3931 | 63.2899 | success |
| math_L5_010 | math_reasoning | 0.7475 | 0.4201 | 58.3797 | success |
| qa_L1_011 | knowledge_qa | 0.8905 | 0.4103 | 65.0378 | success |
| qa_L2_012 | knowledge_qa | 0.8308 | 0.4155 | 62.3127 | success |
| qa_L3_013 | knowledge_qa | 0.8330 | 0.4080 | 62.0500 | success |
| qa_L4_014 | knowledge_qa | 0.7040 | 0.4221 | 56.3051 | success |
| qa_L5_015 | knowledge_qa | 0.5722 | 0.4049 | 48.8562 | success |
| logic_L1_016 | logical_reasoning | 0.8580 | 0.4114 | 63.4698 | success |
| logic_L2_017 | logical_reasoning | 0.8132 | 0.4066 | 60.9907 | success |
| logic_L3_018 | logical_reasoning | 0.8837 | 0.3980 | 64.0852 | success |
| logic_L4_019 | logical_reasoning | 0.7581 | 0.4044 | 58.1245 | success |
| logic_L5_020 | logical_reasoning | 0.5244 | 0.3844 | 45.4410 | success |
| inst_L1_021 | instruction_following | 0.7337 | 0.4308 | 58.2206 | success |
| inst_L2_022 | instruction_following | 0.8495 | 0.4055 | 62.7456 | success |
| inst_L3_023 | instruction_following | 0.7484 | 0.4012 | 57.4814 | success |
| inst_L4_024 | instruction_following | 0.7784 | 0.4168 | 59.7621 | success |
| inst_L5_025 | instruction_following | 0.8282 | 0.3923 | 61.0234 | success |
