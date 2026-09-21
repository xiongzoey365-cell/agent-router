#!/usr/bin/env python3
"""第一阶段：从一次结构化预推理中提取任务无关、无需训练的通用证据。"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from generic_common import (
    OUTPUT_FIELDS,
    as_list,
    best_alignment,
    field_items,
    field_texts,
    lexical_similarity,
    lexical_units,
    mean,
    normalize_text,
    rate,
    read_json,
    regex_count,
    text_value,
    write_json,
)

SELF_ASSESSMENT_PATTERNS = (
    r"置信度", r"信心", r"难度(?:是|为|：|:)", r"能力(?:得分|评分)",
    r"我(?:能|不能|可以|无法)完成", r"已经收敛",
    r"confidence", r"difficulty\s*(?:is|:)", r"capability\s*score",
    r"i\s+(?:can|cannot|can't)\s+(?:solve|complete)", r"converged",
)
FINAL_ANSWER_MARKERS = (
    r"最终答案", r"答案是", r"final answer", r"the answer is",
)
COMMUNICATION_SIGNALS = (
    r"\bagent\b", r"multi-agent", r"handoff", r"message from", r"teammate",
    r"代理", r"智能体", r"交接", r"协作", r"其他成员",
)
MEMORY_SIGNALS = (
    r"previous turn", r"earlier turn", r"\bturn\s*\d+", r"multi-turn",
    r"formerly", r"initially", r"latest state", r"state (?:changed|was changed)",
    r"across all (?:turns|responses)",
    r"上一轮", r"之前", r"先前", r"状态更新", r"最新状态", r"多轮",
)
TOOL_SIGNALS = (
    r"\btool\b", r"call\s+(?:an?\s+)?(?:api|function)", r"browser", r"calculator",
    r"database", r"web search", r"search tool", r"run\s+(?:the\s+)?tests?",
    r"工具", r"调用", r"联网搜索", r"搜索工具", r"查询数据库", r"运行测试", r"数据库",
)
ACTIONABLE_CHECK_PATTERNS = (
    r"compare", r"recompute", r"calculate", r"substitute", r"execute", r"run",
    r"test", r"inspect", r"assert", r"validate", r"verify", r"check",
    r"比较", r"重算", r"计算", r"代入", r"执行", r"运行", r"测试",
    r"检查", r"断言", r"验证", r"核对", r"遍历",
)
CLARIFICATION_PATTERNS = (
    r"clarif", r"ask", r"confirm", r"request", r"澄清", r"询问", r"确认", r"补充",
)
FAILURE_HANDLING_PATTERNS = (
    r"retry", r"fallback", r"if .* fail", r"on error", r"recover",
    r"重试", r"回退", r"失败时", r"异常时", r"恢复",
)
CURRENT_VALUES = {"current", "latest", "active", "当前", "最新", "有效"}
STALE_VALUES = {"stale", "old", "obsolete", "历史", "过期", "旧"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-file",
        default="outputs/phase1_no_training_output_evidence/prereason_outputs.json",
    )
    parser.add_argument(
        "--output-file",
        default="outputs/phase1_no_training_output_evidence/generic_features.json",
    )
    parser.add_argument(
        "--alignment-threshold",
        type=float,
        default=0.12,
        help="只用于报告字面对齐覆盖率，不是能力判定阈值。",
    )
    return parser.parse_args()


def rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def alignment_metrics(
    sources: list[str], targets: list[str], threshold: float
) -> dict[str, Any]:
    details = []
    for index, source in enumerate(sources):
        score, target_index = best_alignment(source, targets)
        details.append({
            "source_index": index,
            "source": source,
            "best_target_index": target_index,
            "best_similarity": rounded(score),
            "above_threshold": bool(target_index is not None and score >= threshold),
        })
    return {
        "source_count": len(sources),
        "target_count": len(targets),
        "mean_best_similarity": rounded(mean(item["best_similarity"] for item in details)),
        "coverage_at_threshold": rounded(rate(item["above_threshold"] for item in details)),
        "details": details,
    }


def nonempty_rate(items: list[Any], key: str) -> float | None:
    return rate(bool(text_value(item.get(key))) for item in items if isinstance(item, dict))


def valid_list_field_rate(parsed: dict[str, Any]) -> float:
    return sum(isinstance(parsed.get(field), list) for field in OUTPUT_FIELDS) / len(OUTPUT_FIELDS)


def dependency_metrics(plan: list[Any]) -> dict[str, Any]:
    normalized = [item if isinstance(item, dict) else {} for item in plan]
    ids = [text_value(item.get("id")) or f"__index_{index}" for index, item in enumerate(normalized)]
    id_to_index = {step_id: index for index, step_id in enumerate(ids)}
    declared_edges: list[tuple[str, str]] = []
    unknown: list[dict[str, str]] = []
    order_violations: list[dict[str, str]] = []
    dependency_lists_valid = 0

    for index, item in enumerate(normalized):
        raw_dependencies = item.get("depends_on", [])
        if isinstance(raw_dependencies, list):
            dependency_lists_valid += 1
        for dependency in as_list(raw_dependencies):
            dependency_id = text_value(dependency)
            declared_edges.append((dependency_id, ids[index]))
            if dependency_id not in id_to_index:
                unknown.append({"step": ids[index], "dependency": dependency_id})
            elif id_to_index[dependency_id] >= index:
                order_violations.append({"step": ids[index], "dependency": dependency_id})

    graph = {step_id: [] for step_id in ids}
    for before, after in declared_edges:
        if before in graph and after in graph:
            graph[before].append(after)

    visiting: set[str] = set()
    visited: set[str] = set()

    def has_cycle(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(has_cycle(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    cycle = any(has_cycle(node) for node in ids if node not in visited)
    nonfirst = normalized[1:]
    return {
        "declared_edge_count": len(declared_edges),
        "dependency_declaration_rate_after_first": rounded(
            rate(bool(as_list(item.get("depends_on"))) for item in nonfirst)
        ),
        "dependency_field_type_valid_rate": rounded(
            dependency_lists_valid / len(normalized) if normalized else None
        ),
        "dependency_reference_valid_rate": rounded(
            1.0 - len(unknown) / len(declared_edges) if declared_edges else None
        ),
        "dependency_order_valid_rate": rounded(
            1.0 - len(order_violations) / len(declared_edges) if declared_edges else None
        ),
        "cycle_detected": cycle,
        "unknown_dependencies": unknown,
        "order_violations": order_violations,
    }


def planning_features(parsed: dict[str, Any], prompt: str, threshold: float) -> dict[str, Any]:
    goals = field_texts(parsed, "goal")
    constraint_items = field_items(parsed, "constraints")
    constraints = field_texts(parsed, "constraints", ("content",))
    plan_items = field_items(parsed, "plan")
    plan_texts = field_texts(parsed, "plan", ("action", "expected_result"))
    conflicts = field_items(parsed, "conflicts")
    conflict_texts = field_texts(parsed, "conflicts", ("content",))
    conflict_actions = field_texts(parsed, "conflicts", ("action",))
    return {
        "evidence_status": "available" if goals or constraints or plan_items else "insufficient",
        "goal_count": len(goals),
        "constraint_count": len(constraints),
        "plan_step_count": len(plan_items),
        "conflict_or_missing_count": len(conflicts),
        "goal_prompt_alignment": alignment_metrics(goals, [prompt], threshold),
        "constraint_prompt_alignment": alignment_metrics(constraints, [prompt], threshold),
        "constraint_plan_alignment": alignment_metrics(constraints, plan_texts, threshold),
        "plan_prompt_alignment": alignment_metrics(plan_texts, [prompt], threshold),
        "constraint_source_completeness": rounded(nonempty_rate(constraint_items, "source")),
        "plan_action_completeness": rounded(nonempty_rate(plan_items, "action")),
        "plan_expected_result_completeness": rounded(nonempty_rate(plan_items, "expected_result")),
        "conflict_action_completeness": rounded(nonempty_rate(conflicts, "action")),
        "conflict_plan_alignment": alignment_metrics(conflict_texts, plan_texts + conflict_actions, threshold),
        "dependencies": dependency_metrics(plan_items),
    }


def instruction_features(result: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    raw = str(result.get("raw_output", ""))
    parser = result.get("parser", {})
    generation = result.get("generation", {})
    present = set(parsed)
    return {
        "evidence_status": "available",
        "strict_json_valid": bool(parser.get("strict_json_valid", False)),
        "recovered_json": bool(parser.get("recovered_json", False)),
        "leading_or_trailing_text": bool(parser.get("leading_or_trailing_text", False)),
        "required_field_completeness": round(
            sum(field in present for field in OUTPUT_FIELDS) / len(OUTPUT_FIELDS), 6
        ),
        "list_field_type_valid_rate": round(valid_list_field_rate(parsed), 6),
        "extra_top_level_fields": sorted(present.difference(OUTPUT_FIELDS)),
        "self_assessment_marker_count": regex_count(SELF_ASSESSMENT_PATTERNS, raw),
        "possible_final_answer_marker_count": regex_count(FINAL_ANSWER_MARKERS, raw),
        "termination_status": generation.get("termination_status"),
        "completed_before_token_budget": generation.get("termination_status") != "token_budget",
    }


def communication_features(parsed: dict[str, Any], prompt: str) -> dict[str, Any]:
    facts = [item for item in field_items(parsed, "facts") if isinstance(item, dict)]
    conflicts = [item for item in field_items(parsed, "conflicts") if isinstance(item, dict)]
    sources = [text_value(item.get("source")) for item in facts if text_value(item.get("source"))]
    opportunity = regex_count(COMMUNICATION_SIGNALS, prompt) > 0
    clarification_count = sum(
        regex_count(CLARIFICATION_PATTERNS, text_value(item.get("action"))) > 0 for item in conflicts
    )
    return {
        "evidence_status": "available" if opportunity else "insufficient",
        "opportunity_signal_detected": opportunity,
        "fact_count": len(facts),
        "fact_source_coverage": rounded(nonempty_rate(facts, "source")),
        "distinct_source_count": len(set(normalize_text(source) for source in sources)),
        "conflict_count": len(conflicts),
        "conflict_action_completeness": rounded(nonempty_rate(conflicts, "action")),
        "clarification_action_count": clarification_count,
        "note": "没有通信机会信号时不解释为通信能力高或低。",
    }


def verification_features(parsed: dict[str, Any], threshold: float) -> dict[str, Any]:
    plan_texts = field_texts(parsed, "plan", ("action", "expected_result"))
    checks = [item for item in field_items(parsed, "verification") if isinstance(item, dict)]
    check_texts = [text_value(item.get("target")) + " " + text_value(item.get("method")) for item in checks]
    methods = [text_value(item.get("method")) for item in checks]
    actionable = [regex_count(ACTIONABLE_CHECK_PATTERNS, method) > 0 for method in methods]
    return {
        "evidence_status": "available" if plan_texts else "insufficient",
        "verification_count": len(checks),
        "target_completeness": rounded(nonempty_rate(checks, "target")),
        "method_completeness": rounded(nonempty_rate(checks, "method")),
        "failure_signal_completeness": rounded(nonempty_rate(checks, "failure_signal")),
        "actionable_method_rate": rounded(rate(actionable)),
        "plan_verification_alignment": alignment_metrics(plan_texts, check_texts, threshold),
        "verification_plan_alignment": alignment_metrics(check_texts, plan_texts, threshold),
    }


def fact_status(item: dict[str, Any]) -> str:
    return normalize_text(item.get("status"))


def possible_current_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = [
        (index, text_value(item.get("content")))
        for index, item in enumerate(facts)
        if fact_status(item) in CURRENT_VALUES and text_value(item.get("content"))
    ]
    conflicts = []
    for (left_index, left), (right_index, right) in combinations(current, 2):
        left_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", left))
        right_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", right))
        if left_numbers and right_numbers and left_numbers != right_numbers:
            similarity = lexical_similarity(left, right)
            if similarity >= 0.18:
                conflicts.append({
                    "left_index": left_index,
                    "right_index": right_index,
                    "similarity": rounded(similarity),
                    "left_numbers": sorted(left_numbers),
                    "right_numbers": sorted(right_numbers),
                })
    return conflicts


def memory_features(parsed: dict[str, Any], prompt: str, threshold: float) -> dict[str, Any]:
    facts = [item for item in field_items(parsed, "facts") if isinstance(item, dict)]
    plan_texts = field_texts(parsed, "plan", ("action", "expected_result"))
    opportunity = regex_count(MEMORY_SIGNALS, prompt) > 0
    current_texts = [
        text_value(item.get("content")) for item in facts if fact_status(item) in CURRENT_VALUES
    ]
    stale_texts = [
        text_value(item.get("content")) for item in facts if fact_status(item) in STALE_VALUES
    ]
    valid_statuses = [
        fact_status(item) in CURRENT_VALUES.union(STALE_VALUES) for item in facts
    ]
    return {
        "evidence_status": "available" if opportunity else "insufficient",
        "opportunity_signal_detected": opportunity,
        "fact_count": len(facts),
        "fact_source_coverage": rounded(nonempty_rate(facts, "source")),
        "fact_status_coverage": rounded(nonempty_rate(facts, "status")),
        "valid_status_rate": rounded(rate(valid_statuses)),
        "current_fact_count": len(current_texts),
        "stale_fact_count": len(stale_texts),
        "current_fact_plan_alignment": alignment_metrics(current_texts, plan_texts, threshold),
        "stale_fact_plan_alignment": alignment_metrics(stale_texts, plan_texts, threshold),
        "possible_current_state_conflicts": possible_current_conflicts(facts),
        "note": "这里只检查状态组织，不能证明模型选择的最新事实确实正确。",
    }


def tool_features(parsed: dict[str, Any], prompt: str) -> dict[str, Any]:
    tools = [item for item in field_items(parsed, "tools") if isinstance(item, dict)]
    facts_text = " ".join(field_texts(parsed, "facts", ("content",)))
    grounding_corpus = normalize_text(prompt + " " + facts_text)
    opportunity = regex_count(TOOL_SIGNALS, prompt) > 0
    argument_key_coverages: list[float] = []
    literal_groundings: list[bool] = []
    failure_handling: list[bool] = []

    for item in tools:
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        sources = item.get("argument_sources") if isinstance(item.get("argument_sources"), dict) else {}
        keys = list(arguments)
        argument_key_coverages.append(
            sum(key in sources and bool(text_value(sources[key])) for key in keys) / len(keys)
            if keys else 0.0
        )
        for value in arguments.values():
            normalized_value = normalize_text(value)
            if normalized_value:
                literal_groundings.append(normalized_value in grounding_corpus)
        combined = text_value(item.get("reason")) + " " + text_value(item.get("success_check"))
        failure_handling.append(regex_count(FAILURE_HANDLING_PATTERNS, combined) > 0)

    return {
        "evidence_status": "available" if opportunity else "insufficient",
        "opportunity_signal_detected": opportunity,
        "tool_count": len(tools),
        "unexpected_tool_plan": bool(tools) and not opportunity,
        "tool_name_completeness": rounded(nonempty_rate(tools, "tool")),
        "reason_completeness": rounded(nonempty_rate(tools, "reason")),
        "nonempty_argument_rate": rounded(
            rate(bool(item.get("arguments")) for item in tools)
        ),
        "argument_source_key_coverage": rounded(mean(argument_key_coverages)),
        "literal_argument_grounding_rate": rounded(rate(literal_groundings)),
        "success_check_completeness": rounded(nonempty_rate(tools, "success_check")),
        "failure_handling_mention_rate": rounded(rate(failure_handling)),
        "note": "这里只评价工具规划产物，不代表真实工具选择和执行正确。",
    }


def general_features(parsed: dict[str, Any], raw: str) -> dict[str, Any]:
    units = lexical_units(raw)
    repeated = len(units) - len(set(units))
    return {
        "raw_character_count": len(raw),
        "lexical_unit_count": len(units),
        "lexical_repetition_ratio": rounded(repeated / len(units) if units else None),
        "field_item_counts": {field: len(field_items(parsed, field)) for field in OUTPUT_FIELDS},
    }


def extract_one(result: dict[str, Any], threshold: float) -> dict[str, Any]:
    if result.get("status") != "success":
        return {
            "task_id": result.get("task_id"),
            "task_type": result.get("task_type"),
            "difficulty_level": result.get("difficulty_level"),
            "status": "error",
            "error": result.get("error", "generation failed"),
        }

    parsed = result.get("parsed_output")
    parsed = parsed if isinstance(parsed, dict) else {}
    prompt = str(result.get("prompt", ""))
    raw = str(result.get("raw_output", ""))
    return {
        "task_id": result.get("task_id"),
        "task_type": result.get("task_type"),
        "difficulty_level": result.get("difficulty_level"),
        "status": "success",
        "general": general_features(parsed, raw),
        "reasoning_planning": planning_features(parsed, prompt, threshold),
        "instruction_following": instruction_features(result, parsed),
        "communication_social": communication_features(parsed, prompt),
        "self_critique_verification": verification_features(parsed, threshold),
        "memory_context": memory_features(parsed, prompt, threshold),
        "tool_planning": tool_features(parsed, prompt),
    }


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.alignment_threshold <= 1.0:
        raise ValueError("alignment-threshold 必须位于 [0, 1]")
    payload = read_json(Path(args.input_file))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("输入文件必须包含 results 数组")

    features = [extract_one(result, args.alignment_threshold) for result in results]
    write_json(Path(args.output_file), {
        "metadata": {
            "method": "phase1_no_training_output_evidence",
            "stage": "phase_1",
            "uses_training": False,
            "uses_task_specific_rules": False,
            "uses_hidden_states": False,
            "produces_capability_score": False,
            "alignment_threshold": args.alignment_threshold,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": args.input_file,
            "interpretation": (
                "所有字段均为预推理产物的通用结构与字面对齐证据，"
                "不代表答案正确率或经过校准的能力概率。"
            ),
        },
        "results": features,
    })


if __name__ == "__main__":
    main()
