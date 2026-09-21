#!/usr/bin/env python3
"""第一阶段无训练输出证据评估的共享定义与纯规则工具。"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


CAPABILITIES = (
    "reasoning_planning",
    "instruction_following",
    "communication_social",
    "self_critique_verification",
    "memory_context",
    "tool_planning",
)

OUTPUT_FIELDS = (
    "goal",
    "constraints",
    "facts",
    "conflicts",
    "plan",
    "verification",
    "tools",
)

SYSTEM_PROMPT = """你只进行一次简短的执行前分析，不要回答最终问题。
不要评价自己的能力、信心、任务难度或是否能够完成任务。
不要输出能力分数、难度等级或“已经收敛”等自我判断。
只输出一个 JSON 对象，不要使用 Markdown 代码块，也不要在 JSON 前后添加文字。
分析内容尽量使用与原任务相同的语言。
必须包含以下字段；不适用的字段输出空数组：
{
  "goal": ["需要达到的目标"],
  "constraints": [{"content": "必须满足的约束", "source": "约束来源"}],
  "facts": [{"content": "当前有效事实", "source": "信息来源", "status": "current或stale"}],
  "conflicts": [{"content": "冲突或必要信息缺失", "action": "处理方式"}],
  "plan": [{"id": "S1", "action": "具体步骤", "depends_on": [], "expected_result": "预期结果"}],
  "verification": [{"target": "验证对象", "method": "具体可执行的验证方法", "failure_signal": "失败判据"}],
  "tools": [{"tool": "工具名称", "reason": "使用原因", "arguments": {}, "argument_sources": {}, "success_check": "成功判据"}]
}"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("输入文件必须包含非空 tasks 数组")
    required = {"task_id", "task_type", "difficulty_level", "prompt"}
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


def extract_json(text: str) -> dict[str, Any]:
    """严格解析失败后尝试恢复，但绝不把恢复结果记成严格格式成功。"""
    stripped = text.strip()
    strict_valid = False
    recovered = False
    error = ""
    value: Any = None
    try:
        value = json.loads(stripped)
        strict_valid = isinstance(value, dict)
        if not strict_valid:
            error = "顶层 JSON 不是对象"
    except json.JSONDecodeError as exc:
        error = f"{exc.msg} (line={exc.lineno}, column={exc.colno})"

    if not strict_valid:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                candidate = json.loads(stripped[start:end + 1])
                if isinstance(candidate, dict):
                    value = candidate
                    recovered = True
            except json.JSONDecodeError:
                pass

    parsed = value if isinstance(value, dict) else {}
    return {
        "parsed": parsed,
        "strict_json_valid": strict_valid,
        "recovered_json": recovered,
        "parse_error": error,
        "leading_or_trailing_text": bool(recovered and not strict_valid),
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(text_value(item) for item in value if text_value(item))
    if isinstance(value, dict):
        return " ".join(
            f"{key} {text_value(content)}" for key, content in value.items() if text_value(content)
        )
    return str(value)


def item_text(item: Any, keys: Iterable[str] = ()) -> str:
    if not isinstance(item, dict):
        return text_value(item)
    selected = list(keys) or list(item.keys())
    return " | ".join(text_value(item.get(key)) for key in selected if text_value(item.get(key)))


def field_items(parsed: dict[str, Any], field: str) -> list[Any]:
    return as_list(parsed.get(field))


def field_texts(parsed: dict[str, Any], field: str, keys: Iterable[str] = ()) -> list[str]:
    return [item_text(item, keys) for item in field_items(parsed, field)]


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[\s\-_]+", " ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff.+*/<>=% ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def lexical_units(value: Any) -> list[str]:
    """英文按词、中文按字切分；不使用任何任务特定词表或训练参数。"""
    text = normalize_text(value)
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?|[\u4e00-\u9fff]", text)


def char_ngrams(value: Any, n: int = 3) -> list[str]:
    text = normalize_text(value).replace(" ", "")
    if not text:
        return []
    if len(text) <= n:
        return [text]
    return [text[index:index + n] for index in range(len(text) - n + 1)]


def cosine_counter(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def lexical_similarity(left: Any, right: Any) -> float:
    """任务无关字面相似度，只作为对齐代理，不代表语义正确。"""
    word_score = cosine_counter(Counter(lexical_units(left)), Counter(lexical_units(right)))
    char_score = cosine_counter(Counter(char_ngrams(left)), Counter(char_ngrams(right)))
    return float(max(0.0, min(1.0, 0.65 * word_score + 0.35 * char_score)))


def best_alignment(source: str, targets: list[str]) -> tuple[float, int | None]:
    if not source or not targets:
        return 0.0, None
    scored = [(lexical_similarity(source, target), index) for index, target in enumerate(targets)]
    return max(scored, default=(0.0, None))


def mean(values: Iterable[float]) -> float | None:
    materialized = [float(value) for value in values]
    return sum(materialized) / len(materialized) if materialized else None


def rate(flags: Iterable[bool]) -> float | None:
    materialized = list(flags)
    return sum(bool(flag) for flag in materialized) / len(materialized) if materialized else None


def regex_count(patterns: Iterable[str], text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.I)) for pattern in patterns)
