#!/usr/bin/env python3
"""用固定、可审计规则将 Judge 事实证据映射到五档能力充分度。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import DIMENSIONS, list_value, read_json, write_json


RUBRIC = (0.0, 0.25, 0.5, 0.75, 1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/model_evidence.json")
    parser.add_argument("--judge-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/judge_evidence.json")
    parser.add_argument("--output-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/sufficiency_results.json")
    return parser.parse_args()


def ratio(good: int, bad: int, empty_default: float = 0.5) -> float:
    total = good + bad
    return good / total if total else empty_default


def quantize(value: float) -> float:
    clipped = max(0.0, min(1.0, value))
    return min(RUBRIC, key=lambda point: (abs(point - clipped), -point))


def observable(evidence: dict[str, Any]) -> bool:
    return evidence.get("observable") is True


def reasoning_score(ev: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    missing = len(list_value(ev.get("missing_key_subtasks")))
    wrong = len(list_value(ev.get("redundant_or_wrong_subtasks")))
    dependencies = len(list_value(ev.get("invalid_dependencies")))
    executable = ev.get("plan_executable")
    raw = 1.0 - min(1.0, 0.25 * missing + 0.2 * wrong + 0.2 * dependencies + (0.35 if executable is False else 0.1 if executable is None else 0.0))
    return quantize(raw), {"raw_rule_value": round(raw, 6), "missing": missing, "wrong": wrong, "invalid_dependencies": dependencies, "plan_executable": executable}


def instruction_score(ev: dict[str, Any], model_item: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    parser = model_item.get("parser", {})
    schema = model_item.get("schema", {})
    strict = bool(parser.get("strict_json_valid"))
    missing_fields = len(list_value(schema.get("missing_fields")))
    wrong_types = len(list_value(schema.get("wrong_type_fields")))
    covered = len(list_value(ev.get("covered_constraints")))
    missed = len(list_value(ev.get("missed_constraints")))
    violated = len(list_value(ev.get("violated_constraints")))
    compliance = ratio(covered, missed + 2 * violated, empty_default=1.0)
    schema_quality = max(0.0, 1.0 - 0.08 * missing_fields - 0.08 * wrong_types)
    role = ev.get("role_appropriate")
    role_quality = 0.0 if role is False else 0.5 if role is None and model_item.get("parsed_output", {}).get("instruction_role", {}).get("role_assumed") else 1.0
    raw = 0.35 * float(strict) + 0.25 * schema_quality + 0.3 * compliance + 0.1 * role_quality
    return quantize(raw), {"raw_rule_value": round(raw, 6), "strict_json": strict, "schema_quality": round(schema_quality, 6), "constraint_compliance": round(compliance, 6), "role_quality": role_quality}


def communication_score(ev: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    understood = len(list_value(ev.get("messages_understood")))
    missed = len(list_value(ev.get("messages_missed")))
    wrong = len(list_value(ev.get("misinterpreted_messages")))
    comprehension = ratio(understood, missed + 2 * wrong)
    clarification = ev.get("clarification_appropriate")
    action = ev.get("coordination_action_valid")
    decisions = [value for value in (clarification, action) if isinstance(value, bool)]
    decision_quality = sum(decisions) / len(decisions) if decisions else 0.5
    raw = 0.7 * comprehension + 0.3 * decision_quality
    return quantize(raw), {"raw_rule_value": round(raw, 6), "message_comprehension": round(comprehension, 6), "decision_quality": round(decision_quality, 6)}


def verification_score(ev: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    risks = len(list_value(ev.get("key_risks")))
    checked = len(list_value(ev.get("risks_checked")))
    invalid_checks = len(list_value(ev.get("invalid_claimed_checks")))
    real_issues = len(list_value(ev.get("real_issues_found")))
    false_issues = len(list_value(ev.get("false_issues")))
    valid_repairs = len(list_value(ev.get("valid_corrections")))
    invalid_repairs = len(list_value(ev.get("invalid_corrections")))
    coverage = min(1.0, checked / risks) if risks else (1.0 if checked else 0.5)
    check_precision = ratio(checked + real_issues, invalid_checks + false_issues)
    repair_quality = ratio(valid_repairs, invalid_repairs, empty_default=1.0 if real_issues == 0 else 0.5)
    raw = 0.55 * coverage + 0.25 * check_precision + 0.2 * repair_quality
    return quantize(raw), {"raw_rule_value": round(raw, 6), "risk_coverage": round(coverage, 6), "check_precision": round(check_precision, 6), "repair_quality": round(repair_quality, 6)}


def memory_score(ev: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    used = len(list_value(ev.get("facts_used_correctly")))
    missed = len(list_value(ev.get("facts_missed")))
    wrong = len(list_value(ev.get("incorrect_or_stale_facts")))
    raw = ratio(used, missed + 2 * wrong)
    return quantize(raw), {"raw_rule_value": round(raw, 6), "correct_facts": used, "missed_facts": missed, "wrong_or_stale_facts": wrong}


def tool_score(ev: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    if not observable(ev): return None, {"reason": "dimension_not_observable"}
    appropriate = len(list_value(ev.get("appropriate_calls")))
    missing = len(list_value(ev.get("missing_calls")))
    wrong = len(list_value(ev.get("unnecessary_or_wrong_calls")))
    valid_args = len(list_value(ev.get("valid_arguments")))
    invalid_args = len(list_value(ev.get("invalid_arguments")))
    selection = ratio(appropriate, missing + 2 * wrong)
    arguments = ratio(valid_args, invalid_args, empty_default=0.5 if appropriate else 1.0)
    components = [selection, arguments]
    if ev.get("interpretation_assessable") is True:
        valid_i = len(list_value(ev.get("valid_interpretations")))
        invalid_i = len(list_value(ev.get("invalid_interpretations")))
        components.append(ratio(valid_i, invalid_i))
    raw = sum(components) / len(components)
    return quantize(raw), {"raw_rule_value": round(raw, 6), "selection": round(selection, 6), "arguments": round(arguments, 6), "interpretation_included": len(components) == 3}


SCORERS = {"reasoning_planning": reasoning_score, "communication": communication_score, "verification": verification_score, "memory_context": memory_score, "tool_use": tool_score}


def score_one(model_item: dict[str, Any], judge_item: dict[str, Any], model_name: str) -> dict[str, Any]:
    if model_item.get("status") != "success" or judge_item.get("status") != "success":
        return {"model": model_name, "task_id": model_item.get("task_id"), "task_type": model_item.get("task_type"), "status": "error", "error": model_item.get("error") or judge_item.get("error") or "upstream failure"}
    evidence = judge_item.get("evidence") if isinstance(judge_item.get("evidence"), dict) else {}
    scores: dict[str, float | None] = {}
    rule_details: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        ev = evidence.get(dimension) if isinstance(evidence.get(dimension), dict) else {}
        result = instruction_score(ev, model_item) if dimension == "instruction_role" else SCORERS[dimension](ev)
        scores[dimension], rule_details[dimension] = result
    observed = [dimension for dimension, value in scores.items() if value is not None]
    overall = sum(scores[name] for name in observed) / len(observed) if observed else None
    minimum = min((scores[name] for name in observed), default=None)
    bottlenecks = [name for name in observed if scores[name] == minimum] if minimum is not None else []
    return {
        "model": model_name, "task_id": model_item.get("task_id"), "task_type": model_item.get("task_type"),
        "observable_dimensions": observed, "capability_sufficiency": scores,
        "overall_sufficiency": None if overall is None else round(overall, 6),
        "relative_difficulty": None if overall is None else round(1.0 - overall, 6),
        "bottleneck": None if minimum is None else {"dimensions": bottlenecks, "sufficiency": minimum},
        "evidence": {name: evidence.get(name) if name in observed else None for name in DIMENSIONS},
        "rule_details": rule_details, "status": "success", "error": "",
    }


def main() -> None:
    args = parse_args()
    model_payload, judge_payload = read_json(Path(args.model_file)), read_json(Path(args.judge_file))
    model_items, judge_items = model_payload.get("results"), judge_payload.get("results")
    if not isinstance(model_items, list) or not isinstance(judge_items, list):
        raise ValueError("两个输入文件都必须包含 results 数组")
    judge_by_id = {str(item.get("task_id")): item for item in judge_items}
    model_name = str(model_payload.get("metadata", {}).get("model", "unknown-model"))
    results = [score_one(item, judge_by_id.get(str(item.get("task_id")), {}), model_name) for item in model_items]
    write_json(Path(args.output_file), {
        "metadata": {"method": "task_conditioned_capability_sufficiency", "stage": "deterministic_scoring", "model_source": args.model_file, "judge_source": args.judge_file, "rubric": list(RUBRIC), "aggregation": "unweighted mean over non-null dimensions", "relative_difficulty_formula": "1 - overall_sufficiency", "uses_training": False, "uses_answer_correctness": False, "judge_assigns_scores": False, "created_at": datetime.now(timezone.utc).isoformat()},
        "results": results,
    })


if __name__ == "__main__":
    main()
