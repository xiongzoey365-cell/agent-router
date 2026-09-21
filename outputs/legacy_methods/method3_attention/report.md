# 想法三实验结果

> 本报告只展示注意力拓扑探针结果，不生成完整答案，也不与 L1–L5 比较。

## 实验配置

- 模型：`/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218`
- 设备：`cuda`
- 精度：`bf16`
- 最后层数：2
- Top 比例：0.1
- 图边阈值：0.1
- 成功/总数：25/25

## 汇总

- 最小分数：47.9024
- 最大分数：59.0030
- 平均分数：53.4929
- 中位数：53.1168
- 平均耗时：119.10 ms
- 最大峰值显存：15819.11 MB

## 逐题结果

| task_id | task_type | 注意力熵 | Top10%集中度 | 图密度 | AttentionLoadScore | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| code_L1_001 | code_generation | 0.6951 | 0.5624 | 0.0920 | 56.6367 | success |
| code_L2_002 | code_generation | 0.6728 | 0.6013 | 0.0482 | 53.5754 | success |
| code_L3_003 | code_generation | 0.6300 | 0.6566 | 0.0318 | 48.6720 | success |
| code_L4_004 | code_generation | 0.6661 | 0.6387 | 0.0162 | 51.3724 | success |
| code_L5_005 | code_generation | 0.6817 | 0.6219 | 0.0134 | 52.9897 | success |
| math_L1_006 | math_reasoning | 0.7102 | 0.5491 | 0.1304 | 58.0557 | success |
| math_L2_007 | math_reasoning | 0.6946 | 0.5738 | 0.0719 | 56.0417 | success |
| math_L3_008 | math_reasoning | 0.7177 | 0.5432 | 0.1011 | 58.7288 | success |
| math_L4_009 | math_reasoning | 0.6908 | 0.5684 | 0.0911 | 56.1218 | success |
| math_L5_010 | math_reasoning | 0.6788 | 0.5713 | 0.1304 | 55.3786 | success |
| qa_L1_011 | knowledge_qa | 0.7172 | 0.5690 | 0.4643 | 57.4080 | success |
| qa_L2_012 | knowledge_qa | 0.6485 | 0.6186 | 0.0580 | 51.4938 | success |
| qa_L3_013 | knowledge_qa | 0.6266 | 0.6686 | 0.0202 | 47.9024 | success |
| qa_L4_014 | knowledge_qa | 0.6457 | 0.6340 | 0.0362 | 50.5894 | success |
| qa_L5_015 | knowledge_qa | 0.6768 | 0.6144 | 0.0206 | 53.1168 | success |
| logic_L1_016 | logical_reasoning | 0.6845 | 0.5799 | 0.0856 | 55.2336 | success |
| logic_L2_017 | logical_reasoning | 0.6761 | 0.5959 | 0.0620 | 54.0083 | success |
| logic_L3_018 | logical_reasoning | 0.6991 | 0.5907 | 0.0233 | 55.4243 | success |
| logic_L4_019 | logical_reasoning | 0.6730 | 0.6217 | 0.0216 | 52.5679 | success |
| logic_L5_020 | logical_reasoning | 0.6724 | 0.6344 | 0.0110 | 51.8958 | success |
| inst_L1_021 | instruction_following | 0.7195 | 0.5394 | 0.1367 | 59.0030 | success |
| inst_L2_022 | instruction_following | 0.6685 | 0.6139 | 0.0329 | 52.7335 | success |
| inst_L3_023 | instruction_following | 0.6571 | 0.6393 | 0.0185 | 50.8936 | success |
| inst_L4_024 | instruction_following | 0.6417 | 0.6608 | 0.0166 | 49.0463 | success |
| inst_L5_025 | instruction_following | 0.6447 | 0.6760 | 0.0094 | 48.4320 | success |
