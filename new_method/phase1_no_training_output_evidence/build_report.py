#!/usr/bin/env python3
"""第一阶段：将通用输出证据整理为 CSV 和 Markdown 分布报告。"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from generic_common import CAPABILITIES, read_json

METRICS = {
    "generated_lexical_units": "general.lexical_unit_count",
    "lexical_repetition_ratio": "general.lexical_repetition_ratio",
    "goal_count": "reasoning_planning.goal_count",
    "constraint_count": "reasoning_planning.constraint_count",
    "plan_step_count": "reasoning_planning.plan_step_count",
    "constraint_prompt_similarity": (
        "reasoning_planning.constraint_prompt_alignment.mean_best_similarity"
    ),
    "constraint_plan_coverage": (
        "reasoning_planning.constraint_plan_alignment.coverage_at_threshold"
    ),
    "plan_prompt_similarity": "reasoning_planning.plan_prompt_alignment.mean_best_similarity",
    "constraint_source_completeness": "reasoning_planning.constraint_source_completeness",
    "plan_action_completeness": "reasoning_planning.plan_action_completeness",
    "plan_expected_result_completeness": (
        "reasoning_planning.plan_expected_result_completeness"
    ),
    "dependency_edge_count": "reasoning_planning.dependencies.declared_edge_count",
    "dependency_reference_valid_rate": (
        "reasoning_planning.dependencies.dependency_reference_valid_rate"
    ),
    "dependency_order_valid_rate": (
        "reasoning_planning.dependencies.dependency_order_valid_rate"
    ),
    "dependency_cycle_detected": "reasoning_planning.dependencies.cycle_detected",
    "strict_json_valid": "instruction_following.strict_json_valid",
    "required_field_completeness": "instruction_following.required_field_completeness",
    "list_field_type_valid_rate": "instruction_following.list_field_type_valid_rate",
    "self_assessment_marker_count": (
        "instruction_following.self_assessment_marker_count"
    ),
    "communication_source_coverage": "communication_social.fact_source_coverage",
    "verification_count": "self_critique_verification.verification_count",
    "verification_method_completeness": (
        "self_critique_verification.method_completeness"
    ),
    "verification_failure_signal_completeness": (
        "self_critique_verification.failure_signal_completeness"
    ),
    "actionable_verification_rate": (
        "self_critique_verification.actionable_method_rate"
    ),
    "plan_verification_coverage": (
        "self_critique_verification.plan_verification_alignment.coverage_at_threshold"
    ),
    "memory_status_coverage": "memory_context.fact_status_coverage",
    "memory_valid_status_rate": "memory_context.valid_status_rate",
    "tool_count": "tool_planning.tool_count",
    "unexpected_tool_plan": "tool_planning.unexpected_tool_plan",
    "tool_argument_source_coverage": "tool_planning.argument_source_key_coverage",
    "tool_literal_argument_grounding_rate": (
        "tool_planning.literal_argument_grounding_rate"
    ),
    "tool_success_check_completeness": "tool_planning.success_check_completeness",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-file",
        default="outputs/phase1_no_training_output_evidence/generic_features.json",
    )
    parser.add_argument(
        "--csv-file",
        default="outputs/phase1_no_training_output_evidence/generic_features.csv",
    )
    parser.add_argument(
        "--report-file",
        default="outputs/phase1_no_training_output_evidence/report.md",
    )
    parser.add_argument(
        "--include-difficulty-groups",
        action="store_true",
        help="只按 L1-L5 分组展示分布；难度等级始终不参与指标计算。",
    )
    return parser.parse_args()


def deep_get(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)) or value is None:
        return value
    return ""


def row_for(result: dict[str, Any]) -> dict[str, Any]:
    row = {
        "task_id": result.get("task_id"),
        "task_type": result.get("task_type"),
        "difficulty_level": result.get("difficulty_level"),
        "status": result.get("status"),
    }
    for capability in CAPABILITIES:
        row[f"{capability}_evidence"] = deep_get(result, f"{capability}.evidence_status")
    for name, path in METRICS.items():
        row[name] = scalar(deep_get(result, path))
    return row


def numeric_summary(results: list[dict[str, Any]], path: str) -> dict[str, Any]:
    dimension = path.split(".", 1)[0]
    values = []
    for result in results:
        if (
            dimension in CAPABILITIES
            and deep_get(result, f"{dimension}.evidence_status") != "available"
            and not path.endswith("unexpected_tool_plan")
        ):
            continue
        value = deep_get(result, path)
        if isinstance(value, bool):
            values.append(float(value))
        elif isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return {"count": 0, "mean": None, "median": None, "minimum": None, "maximum": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def append_summary_table(lines: list[str], title: str, results: list[dict[str, Any]]) -> None:
    lines.extend([
        f"## {title}",
        "",
        "| 指标 | 有效样本 | 均值 | 中位数 | 最小 | 最大 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for name, path in METRICS.items():
        summary = numeric_summary(results, path)
        lines.append(
            f"| {name} | {summary['count']} | {fmt(summary['mean'])} | "
            f"{fmt(summary['median'])} | {fmt(summary['minimum'])} | "
            f"{fmt(summary['maximum'])} |"
        )
    lines.append("")


def main() -> None:
    args = parse_args()
    payload = read_json(Path(args.input_file))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("输入文件必须包含 results 数组")

    csv_path = Path(args.csv_file)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [row_for(result) for result in results]
    fields = list(rows[0]) if rows else [
        "task_id", "task_type", "difficulty_level", "status"
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    successful = [result for result in results if result.get("status") == "success"]
    status_counts = Counter(str(result.get("status")) for result in results)
    lines = [
        "# 第一阶段：无训练通用输出证据报告",
        "",
        "> 本报告只描述一次预推理产物的结构、字面对齐和落地程度，"
        "不表示答案正确率、能力真值或经过校准的成功概率。",
        "",
        "## 运行概况",
        "",
        f"- 总任务数：{len(results)}",
        f"- 成功提取：{len(successful)}",
        f"- 状态分布：{dict(status_counts)}",
        "- 逐任务规则：未使用",
        "- 训练：未使用",
        "- Hidden State：未使用",
        "- 六维融合总分：未生成",
        "",
        "## 能力证据可用性",
        "",
        "| 维度 | available | insufficient |",
        "|---|---:|---:|",
    ]
    for capability in CAPABILITIES:
        statuses = Counter(
            deep_get(result, f"{capability}.evidence_status") for result in successful
        )
        lines.append(
            f"| {capability} | {statuses.get('available', 0)} | "
            f"{statuses.get('insufficient', 0)} |"
        )
    lines.append("")

    append_summary_table(lines, "全部任务的原始指标分布", successful)

    task_types = sorted({str(result.get("task_type")) for result in successful})
    for task_type in task_types:
        subset = [result for result in successful if str(result.get("task_type")) == task_type]
        append_summary_table(lines, f"任务类型：{task_type}", subset)

    if args.include_difficulty_groups:
        levels = sorted({
            result.get("difficulty_level") for result in successful
            if isinstance(result.get("difficulty_level"), int)
        })
        for level in levels:
            subset = [
                result for result in successful
                if result.get("difficulty_level") == level
            ]
            append_summary_table(lines, f"仅报告分组：L{level}", subset)

    lines.extend([
        "## 逐题概览",
        "",
        "| task_id | type | L | JSON | constraints | steps | constraint→plan | checks | plan→check |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for result in successful:
        lines.append(
            f"| {result.get('task_id')} | {result.get('task_type')} | "
            f"{result.get('difficulty_level')} | "
            f"{fmt(deep_get(result, 'instruction_following.strict_json_valid'))} | "
            f"{fmt(deep_get(result, 'reasoning_planning.constraint_count'))} | "
            f"{fmt(deep_get(result, 'reasoning_planning.plan_step_count'))} | "
            f"{fmt(deep_get(result, 'reasoning_planning.constraint_plan_alignment.coverage_at_threshold'))} | "
            f"{fmt(deep_get(result, 'self_critique_verification.verification_count'))} | "
            f"{fmt(deep_get(result, 'self_critique_verification.plan_verification_alignment.coverage_at_threshold'))} |"
        )

    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
