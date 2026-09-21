# Task-conditioned Capability Sufficiency 实验报告

> 分数描述模型与具体任务交互时暴露出的能力充分度，不是模型静态能力或题目客观难度。最终答案正确性未参与评分。

## 概况

- 任务数：25
- 成功评分：25
- 训练：无
- Hidden State：未使用
- 聚合：仅对非 null 维度做无权平均

## 各维度可观察性与分布

| 维度 | 可观察题数 | 均值 | 最小 | 最大 |
|---|---:|---:|---:|---:|
| reasoning_planning | 25 | 1.000 | 1.000 | 1.000 |
| instruction_role | 25 | 0.990 | 0.750 | 1.000 |
| communication | 0 | NA | NA | NA |
| verification | 25 | 0.660 | 0.500 | 1.000 |
| memory_context | 0 | NA | NA | NA |
| tool_use | 0 | NA | NA | NA |

## 瓶颈分布

{'verification': 24, 'reasoning_planning': 7, 'instruction_role': 8}

## 逐题结果

| task_id | type | observable | overall | relative difficulty | bottleneck |
|---|---|---:|---:|---:|---|
| code_L1_001 | code_generation | 3 | 0.833 | 0.167 | verification |
| code_L2_002 | code_generation | 3 | 0.833 | 0.167 | verification |
| code_L3_003 | code_generation | 3 | 0.833 | 0.167 | verification |
| code_L4_004 | code_generation | 3 | 0.833 | 0.167 | verification |
| code_L5_005 | code_generation | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| math_L1_006 | math_reasoning | 3 | 0.833 | 0.167 | verification |
| math_L2_007 | math_reasoning | 3 | 0.833 | 0.167 | verification |
| math_L3_008 | math_reasoning | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| math_L4_009 | math_reasoning | 3 | 0.833 | 0.167 | verification |
| math_L5_010 | math_reasoning | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| qa_L1_011 | knowledge_qa | 3 | 0.833 | 0.167 | verification |
| qa_L2_012 | knowledge_qa | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| qa_L3_013 | knowledge_qa | 3 | 0.833 | 0.167 | verification |
| qa_L4_014 | knowledge_qa | 3 | 0.833 | 0.167 | verification |
| qa_L5_015 | knowledge_qa | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| logic_L1_016 | logical_reasoning | 3 | 0.833 | 0.167 | verification |
| logic_L2_017 | logical_reasoning | 3 | 0.833 | 0.167 | verification |
| logic_L3_018 | logical_reasoning | 3 | 0.833 | 0.167 | verification |
| logic_L4_019 | logical_reasoning | 3 | 0.833 | 0.167 | verification |
| logic_L5_020 | logical_reasoning | 3 | 0.917 | 0.083 | instruction_role |
| inst_L1_021 | instruction_following | 3 | 0.833 | 0.167 | verification |
| inst_L2_022 | instruction_following | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| inst_L3_023 | instruction_following | 3 | 0.833 | 0.167 | verification |
| inst_L4_024 | instruction_following | 3 | 1.000 | 0.000 | reasoning_planning, instruction_role, verification |
| inst_L5_025 | instruction_following | 3 | 0.833 | 0.167 | verification |
