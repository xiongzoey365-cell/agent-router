# 想法一实验结果

> 本报告只展示隐空间探针结果，不评价完整答案，也不与 L1–L5 比较。

## 实验配置

- 模型：`/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- 设备：`cuda`
- 精度：`bf16`
- 生成 Token：40
- 分析 Token：生成序列末尾 20 个
- 最后层数：4
- PCA 维度：64
- 聚类数：8
- 成功/总数：25/25

## 汇总

- 最小分数：31.1512
- 最大分数：66.2174
- 平均分数：51.1729
- 中位数：52.5942
- 平均耗时：1641.10 ms
- 最大峰值显存：15829.96 MB

## 逐题结果

| task_id | task_type | 语义熵 | 轨迹漂移 | LatentLoadScore | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| code_L1_001 | code_generation | 0.7077 | 0.4301 | 56.8909 | success |
| code_L2_002 | code_generation | 0.1897 | 0.4334 | 31.1512 | success |
| code_L3_003 | code_generation | 0.5318 | 0.4484 | 49.0088 | success |
| code_L4_004 | code_generation | 0.6146 | 0.4377 | 52.6156 | success |
| code_L5_005 | code_generation | 0.6696 | 0.3823 | 52.5942 | success |
| math_L1_006 | math_reasoning | 0.8339 | 0.3954 | 61.4644 | success |
| math_L2_007 | math_reasoning | 0.4115 | 0.4258 | 41.8656 | success |
| math_L3_008 | math_reasoning | 0.8237 | 0.4151 | 61.9357 | success |
| math_L4_009 | math_reasoning | 0.6146 | 0.3887 | 50.1660 | success |
| math_L5_010 | math_reasoning | 0.7400 | 0.4062 | 57.3102 | success |
| qa_L1_011 | knowledge_qa | 0.7537 | 0.3990 | 57.6307 | success |
| qa_L2_012 | knowledge_qa | 0.3973 | 0.4307 | 41.3980 | success |
| qa_L3_013 | knowledge_qa | 0.2492 | 0.4199 | 33.4526 | success |
| qa_L4_014 | knowledge_qa | 0.7400 | 0.4258 | 58.2877 | success |
| qa_L5_015 | knowledge_qa | 0.4796 | 0.4163 | 44.7923 | success |
| logic_L1_016 | logical_reasoning | 0.8761 | 0.4238 | 64.9918 | success |
| logic_L2_017 | logical_reasoning | 0.4397 | 0.4138 | 42.6724 | success |
| logic_L3_018 | logical_reasoning | 0.5614 | 0.3939 | 47.7652 | success |
| logic_L4_019 | logical_reasoning | 0.4397 | 0.3893 | 41.4487 | success |
| logic_L5_020 | logical_reasoning | 0.4730 | 0.3819 | 42.7446 | success |
| inst_L1_021 | instruction_following | 0.7968 | 0.4379 | 61.7367 | success |
| inst_L2_022 | instruction_following | 0.9029 | 0.4215 | 66.2174 | success |
| inst_L3_023 | instruction_following | 0.8077 | 0.3940 | 60.0871 | success |
| inst_L4_024 | instruction_following | 0.5263 | 0.4193 | 47.2785 | success |
| inst_L5_025 | instruction_following | 0.6952 | 0.3812 | 53.8166 | success |
