#!/usr/bin/env python3
"""Task-conditioned capability sufficiency 实验的共享定义。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DIMENSIONS = (
    "reasoning_planning",
    "instruction_role",
    "communication",
    "verification",
    "memory_context",
    "tool_use",
)

MODEL_SCHEMA: dict[str, Any] = {
    "reasoning_planning": {"subtasks": [], "dependencies": []},
    "instruction_role": {"constraints_used": [], "role_assumed": None},
    "communication": {
        "messages_used": [],
        "missing_information": [],
        "clarification_needed": False,
        "action": None,
    },
    "verification": {"checks_performed": [], "issues_found": [], "corrections": []},
    "memory_context": {"facts_used": []},
    "tool_use": {"calls": []},
}

MODEL_SYSTEM_PROMPT = """你只需要阅读并分析用户任务，然后暴露最小充分的结构化行为证据。
不要回答用户问题，不要生成最终答案、完整解法、完整代码、完整证明或完整思维过程。
不要评价自己的能力、信心或任务难度；不要给六维能力打分。
只输出一个 JSON 对象，不要使用 Markdown 代码块，不要在 JSON 前后添加文字。
必须严格使用下列结构；不适用的数组保持为空，不适用的可空值使用 null：
{
  "reasoning_planning": {
    "subtasks": ["必要子任务的简短名称"],
    "dependencies": [["前置子任务", "后续子任务"]]
  },
  "instruction_role": {
    "constraints_used": ["实际遵循的重要约束"],
    "role_assumed": null
  },
  "communication": {
    "messages_used": ["实际使用的其他参与者消息"],
    "missing_information": ["完成任务仍缺失的信息"],
    "clarification_needed": false,
    "action": null
  },
  "verification": {
    "checks_performed": ["实际做过的简短检查"],
    "issues_found": ["检查发现的真实问题"],
    "corrections": ["针对问题采取的修正"]
  },
  "memory_context": {"facts_used": ["实际使用的前文或历史事实"]},
  "tool_use": {
    "calls": [{"tool_name": "工具名", "arguments": {}, "result_interpretation": null}]
  }
}
工具未真实执行时，不得虚构工具结果。所有字段只提供判断当前任务条件下行为是否充分所需的最少信息。"""

JUDGE_SCHEMA: dict[str, Any] = {
    "reasoning_planning": {
        "observable": True,
        "missing_key_subtasks": [],
        "redundant_or_wrong_subtasks": [],
        "invalid_dependencies": [],
        "plan_executable": None,
    },
    "instruction_role": {
        "observable": True,
        "important_constraints": [],
        "covered_constraints": [],
        "missed_constraints": [],
        "violated_constraints": [],
        "role_appropriate": None,
    },
    "communication": {
        "observable": False,
        "important_messages": [],
        "messages_understood": [],
        "messages_missed": [],
        "misinterpreted_messages": [],
        "clarification_appropriate": None,
        "coordination_action_valid": None,
    },
    "verification": {
        "observable": True,
        "key_risks": [],
        "risks_checked": [],
        "invalid_claimed_checks": [],
        "real_issues_found": [],
        "false_issues": [],
        "valid_corrections": [],
        "invalid_corrections": [],
    },
    "memory_context": {
        "observable": False,
        "required_context_facts": [],
        "facts_used_correctly": [],
        "facts_missed": [],
        "incorrect_or_stale_facts": [],
    },
    "tool_use": {
        "observable": False,
        "tool_need": "none",
        "appropriate_calls": [],
        "missing_calls": [],
        "unnecessary_or_wrong_calls": [],
        "valid_arguments": [],
        "invalid_arguments": [],
        "interpretation_assessable": False,
        "valid_interpretations": [],
        "invalid_interpretations": [],
    },
}

JUDGE_SYSTEM_PROMPT = """你是行为证据提取器，不是总评分器。只根据任务文本和被测模型主动暴露的结构化输出提取事实性证据。
被测模型没有生成最终答案；禁止要求、补写或推断答案和隐藏思维链。禁止评价模型的一般能力；禁止输出任何能力分数、总体分数或难度分数。
不要使用数据集答案、难度标签或任务外参考答案。只判断所声明的计划、约束处理、沟通、检查、上下文使用和工具行为对当前任务是否充分。
observable=true 仅表示任务确实提供了观察该维度的机会：reasoning_planning 和 instruction_role 通常可观察；communication 仅在任务含其他参与者消息或协作要求时可观察；memory_context 仅在任务依赖前文、历史状态或长上下文事实时可观察；tool_use 仅在任务明确允许/要求工具，或不用工具无法合理完成时可观察；verification 在任务存在可检查风险且输出能提供检查证据时可观察。
tool_need 只能是 none、optional、required。没有真实工具结果时，interpretation_assessable=false，且不得评价结果解释。
只输出一个严格 JSON 对象，不要 Markdown，不要附加文字。必须使用给定结构；未知布尔项用 null，未知列表用空数组。列表内每项应是简短、可核查的证据描述。"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("输入文件必须包含非空 tasks 数组")
    required = {"task_id", "task_type", "prompt"}
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"tasks[{index}] 必须是对象")
        missing = required.difference(task)
        if missing:
            raise ValueError(f"tasks[{index}] 缺少字段: {sorted(missing)}")
        task_id = str(task["task_id"])
        if task_id in seen:
            raise ValueError(f"重复 task_id: {task_id}")
        seen.add(task_id)
    return tasks


def parse_json_object(text: str) -> dict[str, Any]:
    """返回解析结果和严格性信息；恢复结果不得冒充严格 JSON。"""
    stripped = text.strip()
    value: Any = None
    strict = False
    error = ""
    try:
        value = json.loads(stripped)
        strict = isinstance(value, dict)
        if not strict:
            error = "顶层 JSON 不是对象"
    except json.JSONDecodeError as exc:
        error = f"{exc.msg} (line={exc.lineno}, column={exc.colno})"
    recovered = False
    if not strict:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                candidate = json.loads(stripped[start:end + 1])
                if isinstance(candidate, dict):
                    value, recovered = candidate, True
            except json.JSONDecodeError:
                pass
    return {
        "parsed": value if isinstance(value, dict) else {},
        "strict_json_valid": strict,
        "recovered_json": recovered,
        "parse_error": error,
    }


def schema_diagnostics(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    wrong_types: list[str] = []
    extras: list[str] = []

    def walk(value: Any, expected: Any, path: str) -> None:
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                wrong_types.append(path or "$")
                return
            for key, child in expected.items():
                child_path = f"{path}.{key}" if path else key
                if key not in value:
                    missing.append(child_path)
                else:
                    walk(value[key], child, child_path)
            extras.extend(f"{path}.{key}" if path else key for key in value if key not in expected)
        elif isinstance(expected, list) and not isinstance(value, list):
            wrong_types.append(path)
        elif isinstance(expected, bool) and not isinstance(value, bool):
            wrong_types.append(path)
        elif isinstance(expected, str) and not isinstance(value, str):
            wrong_types.append(path)
        elif expected is None and value is not None:
            # null in the template denotes a nullable scalar, not a hard type requirement.
            return

    walk(payload, schema, "")
    return {"missing_fields": missing, "wrong_type_fields": wrong_types, "extra_fields": extras}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
