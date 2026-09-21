# 最小结构化证据 Hidden-State 轨报告

> 本报告与 LLM-Judge 轨完全独立。latent load 仅为未校准的隐藏状态变化代理，不是能力充分度、答案正确率或客观难度。

## 概况

- 总任务数：25
- 成功提取：25
- 最终答案：未生成
- Judge 输出：未读取
- 两轨融合：未进行

## 字段可测量性与潜在负荷

| 字段 | available | empty | too_short | mean | min | max |
|---|---:|---:|---:|---:|---:|---:|
| reasoning_planning | 25 | 0 | 0 | 0.3983 | 0.3764 | 0.4339 |
| instruction_role | 25 | 0 | 0 | 0.4105 | 0.3898 | 0.4301 |
| communication | 4 | 21 | 0 | 0.3964 | 0.3750 | 0.4064 |
| verification | 25 | 0 | 0 | 0.4004 | 0.3491 | 0.4217 |
| memory_context | 8 | 17 | 0 | 0.4030 | 0.3824 | 0.4279 |
| tool_use | 0 | 25 | 0 | NA | NA | NA |

## 逐题结果

| task_id | type | available fields | overall latent load |
|---|---|---:|---:|
| code_L1_001 | code_generation | 3 | 0.4108 |
| code_L2_002 | code_generation | 3 | 0.4175 |
| code_L3_003 | code_generation | 3 | 0.4081 |
| code_L4_004 | code_generation | 3 | 0.3975 |
| code_L5_005 | code_generation | 3 | 0.3918 |
| math_L1_006 | math_reasoning | 3 | 0.4149 |
| math_L2_007 | math_reasoning | 3 | 0.4134 |
| math_L3_008 | math_reasoning | 3 | 0.4057 |
| math_L4_009 | math_reasoning | 3 | 0.4165 |
| math_L5_010 | math_reasoning | 3 | 0.4070 |
| qa_L1_011 | knowledge_qa | 4 | 0.4231 |
| qa_L2_012 | knowledge_qa | 4 | 0.4137 |
| qa_L3_013 | knowledge_qa | 4 | 0.3983 |
| qa_L4_014 | knowledge_qa | 4 | 0.4013 |
| qa_L5_015 | knowledge_qa | 5 | 0.3798 |
| logic_L1_016 | logical_reasoning | 3 | 0.4147 |
| logic_L2_017 | logical_reasoning | 5 | 0.3975 |
| logic_L3_018 | logical_reasoning | 3 | 0.3920 |
| logic_L4_019 | logical_reasoning | 3 | 0.3907 |
| logic_L5_020 | logical_reasoning | 5 | 0.3947 |
| inst_L1_021 | instruction_following | 3 | 0.4106 |
| inst_L2_022 | instruction_following | 3 | 0.3943 |
| inst_L3_023 | instruction_following | 3 | 0.3813 |
| inst_L4_024 | instruction_following | 5 | 0.4113 |
| inst_L5_025 | instruction_following | 3 | 0.3930 |
