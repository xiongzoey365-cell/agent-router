#!/usr/bin/env python3
"""Extract text and raw-hidden-state difficulty signals from both experiment arms."""

from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F


HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "outputs"
DEFAULT_OUTPUT = HERE / "difficulty_signal_analysis"

STATUS = {
    "code_L1_001": "correct", "code_L2_002": "correct",
    "code_L3_003": "correct", "code_L4_004": "correct",
    "code_L5_005": "partial",
    "math_L1_006": "correct", "math_L2_007": "correct",
    "math_L3_008": "correct", "math_L4_009": "correct",
    "math_L5_010": "correct",
    "qa_L1_011": "correct", "qa_L2_012": "correct",
    "qa_L3_013": "correct", "qa_L4_014": "partial",
    "qa_L5_015": "partial",
    "logic_L1_016": "correct", "logic_L2_017": "correct",
    "logic_L3_018": "partial", "logic_L4_019": "correct",
    "logic_L5_020": "correct",
    "inst_L1_021": "correct", "inst_L2_022": "incorrect",
    "inst_L3_023": "incorrect", "inst_L4_024": "correct",
    "inst_L5_025": "incorrect",
}

LEXICONS = {
    "verification_mentions": (
        "check", "verify", "validate", "test", "review", "confirm",
        "检查", "验证", "测试", "复核", "确认",
    ),
    "uncertainty_mentions": (
        "uncertain", "ambigu", "conflict", "contradiction", "possible",
        "if", "whether", "不确定", "歧义", "冲突", "矛盾", "可能", "如果",
    ),
    "tool_mentions": (
        "tool", "python", "calculator", "search", "database", "execute",
        "工具", "计算器", "检索", "搜索", "代码执行", "运行",
    ),
    "absence_mentions": (
        "not applicable", "not evident", "no obvious", "does not require",
        "不适用", "未体现", "没有明显体现", "不需要",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-depth-tokens", type=int, default=1024)
    return parser.parse_args()


def cosine_distance_rows(left: torch.Tensor, right: torch.Tensor) -> torch.Tensor:
    return 1.0 - F.cosine_similarity(left.float(), right.float(), dim=-1, eps=1e-8)


def selected_positions(length: int, maximum: int) -> torch.Tensor:
    if length <= maximum:
        return torch.arange(length, dtype=torch.long)
    return torch.from_numpy(np.linspace(0, length - 1, maximum).round().astype(np.int64))


def safe_mean(values: torch.Tensor) -> float | None:
    return float(values.mean().item()) if values.numel() else None


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def hidden_metrics(path: Path, record: dict[str, Any], max_depth_tokens: int) -> dict[str, Any]:
    artifact = torch.load(path, map_location="cpu", weights_only=False)
    states: tuple[torch.Tensor, ...] = artifact["hidden_states"]
    prompt_count = int(artifact["prompt_token_count"])
    generated_count = int(artifact["generated_token_count"])
    # EOS is a termination marker rather than visible response content.
    visible_count = generated_count - (1 if record["generation"]["termination"] == "eos" else 0)
    visible_count = max(0, visible_count)
    start, end = prompt_count, prompt_count + visible_count

    final = states[-1][0, start:end]
    adjacent = cosine_distance_rows(final[1:], final[:-1]) if visible_count > 1 else torch.empty(0)
    early_n = min(32, adjacent.numel())
    terminal_n = min(32, adjacent.numel())
    temporal_mean = safe_mean(adjacent)
    temporal_early = safe_mean(adjacent[:early_n])
    temporal_terminal = safe_mean(adjacent[-terminal_n:])

    if visible_count > 1:
        anchor = final[0].float().unsqueeze(0)
        anchor_distance = cosine_distance_rows(final[1:], anchor.expand(visible_count - 1, -1))
    else:
        anchor_distance = torch.empty(0)

    positions = selected_positions(visible_count, max_depth_tokens)
    depth_means = []
    depth_terminal_means = []
    pair_start = max(1, len(states) - 8)
    for index in range(pair_start, len(states)):
        left = states[index - 1][0, start:end]
        right = states[index][0, start:end]
        if positions.numel():
            distances = cosine_distance_rows(left[positions], right[positions])
            depth_means.append(float(distances.mean().item()))
            tail_positions = positions[-min(32, positions.numel()):]
            terminal_distances = cosine_distance_rows(left[tail_positions], right[tail_positions])
            depth_terminal_means.append(float(terminal_distances.mean().item()))
        del left, right

    norms = torch.linalg.vector_norm(final.float(), dim=-1) if visible_count else torch.empty(0)
    norm_mean = safe_mean(norms)
    norm_std = float(norms.std(unbiased=False).item()) if norms.numel() else None
    result = {
        "visible_generated_tokens": visible_count,
        "temporal_distance_mean": temporal_mean,
        "temporal_distance_early32": temporal_early,
        "temporal_distance_terminal32": temporal_terminal,
        "temporal_terminal_to_early_ratio": safe_ratio(temporal_terminal, temporal_early),
        "distance_from_first_mean": safe_mean(anchor_distance),
        "distance_from_first_terminal32": safe_mean(anchor_distance[-min(32, anchor_distance.numel()):]),
        "late8_depth_update_mean": float(np.mean(depth_means)) if depth_means else None,
        "late8_depth_update_terminal": float(np.mean(depth_terminal_means)) if depth_terminal_means else None,
        "final_state_norm_mean": norm_mean,
        "final_state_norm_cv": (norm_std / norm_mean if norm_mean and norm_std is not None else None),
    }
    del artifact, states, final, adjacent, anchor_distance, norms
    gc.collect()
    return result


def count_mentions(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term.lower()) for term in terms)


def text_metrics(record: dict[str, Any]) -> dict[str, Any]:
    text = str(record["raw_output"])
    dimension_labels = (
        "推理与规划", "指令遵循与角色遵从", "通信与社会推理",
        "自我批评与验证", "记忆与上下文管理", "工具使用与动作落地",
    )
    result = {
        "output_characters": len(text),
        "output_lines": len(text.splitlines()),
        "dimension_labels_present": sum(label in text for label in dimension_labels),
    }
    result.update({name: count_mentions(text, terms) for name, terms in LEXICONS.items()})
    return result


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for arm in ("six_dimension", "no_prompt_baseline"):
        records_dir = input_dir / arm / "records"
        for record_path in sorted(records_dir.glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            hidden_path = input_dir / record["artifacts"]["raw_hidden_states"]
            row = {
                "arm": arm,
                "task_id": record["task_id"],
                "task_type": record["task_type"],
                "difficulty_level": record["difficulty_level"],
                "answer_status": STATUS[record["task_id"]],
                "prompt_tokens": record["generation"]["prompt_tokens"],
                "generated_tokens": record["generation"]["generated_tokens"],
                "termination": record["generation"]["termination"],
                **text_metrics(record),
                **hidden_metrics(hidden_path, record, args.max_depth_tokens),
            }
            rows.append({key: json_safe(value) for key, value in row.items()})
            print(f"analyzed {arm}/{record['task_id']}", flush=True)

    fieldnames = list(rows[0])
    with (output_dir / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "metrics.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"complete: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
