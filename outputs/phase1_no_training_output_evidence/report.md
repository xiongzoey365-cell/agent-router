# 第一阶段：无训练通用输出证据报告

> 本报告只描述一次预推理产物的结构、字面对齐和落地程度，不表示答案正确率、能力真值或经过校准的成功概率。

## 运行概况

- 总任务数：25
- 成功提取：25
- 状态分布：{'success': 25}
- 逐任务规则：未使用
- 训练：未使用
- Hidden State：未使用
- 六维融合总分：未生成

## 能力证据可用性

| 维度 | available | insufficient |
|---|---:|---:|
| reasoning_planning | 13 | 12 |
| instruction_following | 25 | 0 |
| communication_social | 0 | 25 |
| self_critique_verification | 13 | 12 |
| memory_context | 1 | 24 |
| tool_planning | 0 | 25 |

## 全部任务的原始指标分布

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 25 | 187.9200 | 196.0000 | 3.0000 | 323.0000 |
| lexical_repetition_ratio | 25 | 0.5181 | 0.5311 | 0.0000 | 0.7156 |
| goal_count | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 13 | 1.3846 | 1.0000 | 1.0000 | 4.0000 |
| plan_step_count | 13 | 1.4615 | 1.0000 | 1.0000 | 3.0000 |
| constraint_prompt_similarity | 13 | 0.3660 | 0.3523 | 0.0000 | 0.6921 |
| constraint_plan_coverage | 13 | 0.8269 | 1.0000 | 0.0000 | 1.0000 |
| plan_prompt_similarity | 13 | 0.3781 | 0.4072 | 0.0000 | 0.6967 |
| constraint_source_completeness | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 13 | 0.4615 | 0.0000 | 0.0000 | 2.0000 |
| dependency_reference_valid_rate | 4 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_order_valid_rate | 4 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_cycle_detected | 13 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 25 | 0.5200 | 1.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 25 | 0.5200 | 1.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 25 | 0.5200 | 1.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 25 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 13 | 0.7692 | 1.0000 | 0.0000 | 1.0000 |
| plan_verification_coverage | 13 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 25 | 0.5200 | 1.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 任务类型：code_generation

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 5 | 204.6000 | 209.0000 | 164.0000 | 226.0000 |
| lexical_repetition_ratio | 5 | 0.5460 | 0.5392 | 0.4634 | 0.6239 |
| goal_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_step_count | 3 | 2.0000 | 2.0000 | 1.0000 | 3.0000 |
| constraint_prompt_similarity | 3 | 0.5418 | 0.6484 | 0.2848 | 0.6921 |
| constraint_plan_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_prompt_similarity | 3 | 0.5327 | 0.5389 | 0.4168 | 0.6425 |
| constraint_source_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 3 | 1.0000 | 1.0000 | 0.0000 | 2.0000 |
| dependency_reference_valid_rate | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_order_valid_rate | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_cycle_detected | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_verification_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 任务类型：instruction_following

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 5 | 157.4000 | 194.0000 | 3.0000 | 220.0000 |
| lexical_repetition_ratio | 5 | 0.4340 | 0.5287 | 0.0000 | 0.6000 |
| goal_count | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 1 | 4.0000 | 4.0000 | 4.0000 | 4.0000 |
| plan_step_count | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_prompt_similarity | 1 | 0.5403 | 0.5403 | 0.5403 | 0.5403 |
| constraint_plan_coverage | 1 | 0.7500 | 0.7500 | 0.7500 | 0.7500 |
| plan_prompt_similarity | 1 | 0.4072 | 0.4072 | 0.4072 | 0.4072 |
| constraint_source_completeness | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dependency_reference_valid_rate | 0 | NA | NA | NA | NA |
| dependency_order_valid_rate | 0 | NA | NA | NA | NA |
| dependency_cycle_detected | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 5 | 0.2000 | 0.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 5 | 0.2000 | 0.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 5 | 0.2000 | 0.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_verification_coverage | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 5 | 0.2000 | 0.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 任务类型：knowledge_qa

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 5 | 221.8000 | 219.0000 | 153.0000 | 323.0000 |
| lexical_repetition_ratio | 5 | 0.5042 | 0.4575 | 0.4247 | 0.6409 |
| goal_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_step_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_prompt_similarity | 3 | 0.1309 | 0.0000 | 0.0000 | 0.3928 |
| constraint_plan_coverage | 3 | 0.6667 | 1.0000 | 0.0000 | 1.0000 |
| plan_prompt_similarity | 3 | 0.2322 | 0.0000 | 0.0000 | 0.6967 |
| constraint_source_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dependency_reference_valid_rate | 0 | NA | NA | NA | NA |
| dependency_order_valid_rate | 0 | NA | NA | NA | NA |
| dependency_cycle_detected | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 3 | 0.6667 | 1.0000 | 0.0000 | 1.0000 |
| plan_verification_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 任务类型：logical_reasoning

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 5 | 175.6000 | 168.0000 | 121.0000 | 218.0000 |
| lexical_repetition_ratio | 5 | 0.5693 | 0.5417 | 0.4463 | 0.7156 |
| goal_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 3 | 1.6667 | 1.0000 | 1.0000 | 3.0000 |
| plan_step_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_prompt_similarity | 3 | 0.3624 | 0.3523 | 0.1054 | 0.6295 |
| constraint_plan_coverage | 3 | 0.6667 | 1.0000 | 0.0000 | 1.0000 |
| plan_prompt_similarity | 3 | 0.3705 | 0.3231 | 0.2698 | 0.5186 |
| constraint_source_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dependency_reference_valid_rate | 0 | NA | NA | NA | NA |
| dependency_order_valid_rate | 0 | NA | NA | NA | NA |
| dependency_cycle_detected | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 3 | 0.6667 | 1.0000 | 0.0000 | 1.0000 |
| plan_verification_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 任务类型：math_reasoning

| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |
|---|---:|---:|---:|---:|---:|
| generated_lexical_units | 5 | 180.2000 | 184.0000 | 115.0000 | 216.0000 |
| lexical_repetition_ratio | 5 | 0.5372 | 0.5311 | 0.4783 | 0.6157 |
| goal_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| constraint_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_step_count | 3 | 2.0000 | 2.0000 | 1.0000 | 3.0000 |
| constraint_prompt_similarity | 3 | 0.3708 | 0.3035 | 0.2283 | 0.5805 |
| constraint_plan_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_prompt_similarity | 3 | 0.3674 | 0.3432 | 0.3366 | 0.4222 |
| constraint_source_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_action_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| plan_expected_result_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_edge_count | 3 | 1.0000 | 1.0000 | 0.0000 | 2.0000 |
| dependency_reference_valid_rate | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_order_valid_rate | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dependency_cycle_detected | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| strict_json_valid | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| required_field_completeness | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| list_field_type_valid_rate | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| self_assessment_marker_count | 5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| communication_source_coverage | 0 | NA | NA | NA | NA |
| verification_count | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_method_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| verification_failure_signal_completeness | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| actionable_verification_rate | 3 | 0.6667 | 1.0000 | 0.0000 | 1.0000 |
| plan_verification_coverage | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| memory_status_coverage | 0 | NA | NA | NA | NA |
| memory_valid_status_rate | 0 | NA | NA | NA | NA |
| tool_count | 0 | NA | NA | NA | NA |
| unexpected_tool_plan | 5 | 0.6000 | 1.0000 | 0.0000 | 1.0000 |
| tool_argument_source_coverage | 0 | NA | NA | NA | NA |
| tool_literal_argument_grounding_rate | 0 | NA | NA | NA | NA |
| tool_success_check_completeness | 0 | NA | NA | NA | NA |

## 逐题概览

| task_id | type | L | JSON | constraints | steps | constraint→plan | checks | plan→check |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| code_L1_001 | code_generation | 1 | True | 1 | 3 | 1.0000 | 1 | 1.0000 |
| code_L2_002 | code_generation | 2 | True | 1 | 2 | 1.0000 | 1 | 1.0000 |
| code_L3_003 | code_generation | 3 | True | 1 | 1 | 1.0000 | 1 | 1.0000 |
| code_L4_004 | code_generation | 4 | False | 0 | 0 | NA | 0 | NA |
| code_L5_005 | code_generation | 5 | False | 0 | 0 | NA | 0 | NA |
| math_L1_006 | math_reasoning | 1 | True | 1 | 1 | 1.0000 | 1 | 1.0000 |
| math_L2_007 | math_reasoning | 2 | True | 1 | 3 | 1.0000 | 1 | 1.0000 |
| math_L3_008 | math_reasoning | 3 | False | 0 | 0 | NA | 0 | NA |
| math_L4_009 | math_reasoning | 4 | True | 1 | 2 | 1.0000 | 1 | 1.0000 |
| math_L5_010 | math_reasoning | 5 | False | 0 | 0 | NA | 0 | NA |
| qa_L1_011 | knowledge_qa | 1 | True | 1 | 1 | 1.0000 | 1 | 1.0000 |
| qa_L2_012 | knowledge_qa | 2 | True | 1 | 1 | 1.0000 | 1 | 1.0000 |
| qa_L3_013 | knowledge_qa | 3 | True | 1 | 1 | 0.0000 | 1 | 1.0000 |
| qa_L4_014 | knowledge_qa | 4 | False | 0 | 0 | NA | 0 | NA |
| qa_L5_015 | knowledge_qa | 5 | False | 0 | 0 | NA | 0 | NA |
| logic_L1_016 | logical_reasoning | 1 | True | 1 | 1 | 1.0000 | 1 | 1.0000 |
| logic_L2_017 | logical_reasoning | 2 | True | 1 | 1 | 0.0000 | 1 | 1.0000 |
| logic_L3_018 | logical_reasoning | 3 | False | 0 | 0 | NA | 0 | NA |
| logic_L4_019 | logical_reasoning | 4 | False | 0 | 0 | NA | 0 | NA |
| logic_L5_020 | logical_reasoning | 5 | True | 3 | 1 | 1.0000 | 1 | 1.0000 |
| inst_L1_021 | instruction_following | 1 | False | 0 | 0 | NA | 0 | NA |
| inst_L2_022 | instruction_following | 2 | True | 4 | 1 | 0.7500 | 1 | 1.0000 |
| inst_L3_023 | instruction_following | 3 | False | 0 | 0 | NA | 0 | NA |
| inst_L4_024 | instruction_following | 4 | False | 0 | 0 | NA | 0 | NA |
| inst_L5_025 | instruction_following | 5 | False | 0 | 0 | NA | 0 | NA |
