# 想法一实验结果

> 本报告只展示隐空间探针结果，不评价完整答案，也不与 L1–L5 比较。

## 实验配置

- 模型：`/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- 设备：`cuda`
- 精度：`bf16`
- 生成 Token：60
- 分析 Token：生成序列末尾 20 个
- 最后层数：4
- PCA 维度：64
- 聚类数：8
- 成功/总数：25/25

## 汇总

- 最小分数：29.7762
- 最大分数：59.1961
- 平均分数：45.0748
- 中位数：45.3868
- 平均耗时：2357.02 ms
- 最大峰值显存：15844.40 MB

## 逐题结果

| task_id | task_type | 语义熵 | 轨迹漂移 | LatentLoadScore | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| code_L1_001 | code_generation | 0.2947 | 0.4151 | 35.4904 | success |
| code_L2_002 | code_generation | 0.5710 | 0.4251 | 49.8037 | success |
| code_L3_003 | code_generation | 0.2406 | 0.4544 | 34.7520 | success |
| code_L4_004 | code_generation | 0.3973 | 0.4248 | 41.1026 | success |
| code_L5_005 | code_generation | 0.5337 | 0.4009 | 46.7280 | success |
| math_L1_006 | math_reasoning | 0.4121 | 0.4191 | 41.5556 | success |
| math_L2_007 | math_reasoning | 0.4802 | 0.3894 | 43.4807 | success |
| math_L3_008 | math_reasoning | 0.3856 | 0.4312 | 40.8378 | success |
| math_L4_009 | math_reasoning | 0.5337 | 0.3840 | 45.8825 | success |
| math_L5_010 | math_reasoning | 0.7155 | 0.4293 | 57.2390 | success |
| qa_L1_011 | knowledge_qa | 0.3847 | 0.4162 | 40.0444 | success |
| qa_L2_012 | knowledge_qa | 0.6469 | 0.4086 | 52.7739 | success |
| qa_L3_013 | knowledge_qa | 0.7761 | 0.4079 | 59.1961 | success |
| qa_L4_014 | knowledge_qa | 0.4930 | 0.4148 | 45.3868 | success |
| qa_L5_015 | knowledge_qa | 0.2033 | 0.3922 | 29.7762 | success |
| logic_L1_016 | logical_reasoning | 0.3513 | 0.3890 | 37.0176 | success |
| logic_L2_017 | logical_reasoning | 0.6696 | 0.4083 | 53.8937 | success |
| logic_L3_018 | logical_reasoning | 0.6203 | 0.4019 | 51.1096 | success |
| logic_L4_019 | logical_reasoning | 0.5605 | 0.3943 | 47.7387 | success |
| logic_L5_020 | logical_reasoning | 0.4263 | 0.3771 | 40.1703 | success |
| inst_L1_021 | instruction_following | 0.2492 | 0.4265 | 33.7831 | success |
| inst_L2_022 | instruction_following | 0.6880 | 0.3938 | 54.0900 | success |
| inst_L3_023 | instruction_following | 0.5941 | 0.4059 | 49.9999 | success |
| inst_L4_024 | instruction_following | 0.3856 | 0.4204 | 40.2989 | success |
| inst_L5_025 | instruction_following | 0.7073 | 0.3870 | 54.7179 | success |
