#!/usr/bin/env python3
"""为 Hidden-State 向量序列收敛实验生成 CSV 与 Markdown 报告。"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any

from common import DIMENSIONS, read_json


SCALARS = (
    "adjacent_window_distance_mean",
    "distance_to_terminal_mean",
    "early_late_decay",
    "convergence_slope",
    "terminal_stability",
    "convergence_point_fraction_or_one",
    "converged_layer_rate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    base = "outputs/task_conditioned_capability_sufficiency_no_answer/hidden_state_convergence"
    parser.add_argument("--input-file", default=f"{base}/convergence_metrics.json")
    parser.add_argument("--csv-file", default=f"{base}/convergence_metrics.csv")
    parser.add_argument("--report-file", default=f"{base}/report.md")
    return parser.parse_args()


def fmt(value: Any) -> str:
    return "NA" if value is None else f"{value:.6f}" if isinstance(value, float) else str(value)


def main() -> None:
    args = parse_args()
    payload = read_json(Path(args.input_file))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("输入文件必须包含 results 数组")

    rows = []
    for item in results:
        overall = item.get("overall_convergence", {})
        aggregate = overall.get("aggregate") if isinstance(overall.get("aggregate"), dict) else {}
        row = {
            "task_id": item.get("task_id"),
            "task_type": item.get("task_type"),
            "status": item.get("status"),
            "content_tokens": item.get("diagnostics", {}).get("content_tokens"),
            "window_count": overall.get("window_count"),
        }
        row.update({name: aggregate.get(name) for name in SCALARS})
        for dimension in DIMENSIONS:
            field = item.get("dimension_convergence", {}).get(dimension, {})
            row[f"{dimension}_status"] = field.get("measurement_status")
            row[f"{dimension}_content_tokens"] = field.get("content_token_count")
            field_aggregate = field.get("aggregate") if isinstance(field.get("aggregate"), dict) else {}
            row[f"{dimension}_terminal_stability"] = field_aggregate.get("terminal_stability")
            row[f"{dimension}_decay"] = field_aggregate.get("early_late_decay")
        rows.append(row)

    csv_path = Path(args.csv_file)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["task_id"])
        writer.writeheader()
        writer.writerows(rows)

    successful = [item for item in results if item.get("status") == "success"]
    available = [
        item for item in successful
        if item.get("overall_convergence", {}).get("measurement_status") == "available"
    ]
    lines = [
        "# Hidden-State 向量序列收敛报告",
        "",
        "> 只分析真实 Hidden-State 向量窗口的收敛；不分析 token 文本变化，不使用分散熵，不生成或融合总体难度分数。",
        "",
        "## 概况",
        "",
        f"- 总任务数：{len(results)}",
        f"- 成功前向：{len(successful)}",
        f"- 总体收敛可测：{len(available)}",
        "- 最终答案：未生成",
        "- Judge 输出：未读取",
        "",
        "## 总体收敛指标分布",
        "",
        "| 指标 | N | 均值 | 最小 | 最大 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in SCALARS:
        values = [
            item["overall_convergence"]["aggregate"].get(name)
            for item in available
            if item["overall_convergence"]["aggregate"].get(name) is not None
        ]
        lines.append(
            f"| {name} | {len(values)} | "
            f"{fmt(statistics.fmean(values) if values else None)} | "
            f"{fmt(min(values) if values else None)} | "
            f"{fmt(max(values) if values else None)} |"
        )

    lines.extend([
        "",
        "## 逐题总体收敛",
        "",
        "| task_id | type | content tokens | windows | adjacent distance | terminal distance | decay | slope | terminal stability | convergence point |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for item in available:
        overall = item["overall_convergence"]
        aggregate = overall["aggregate"]
        lines.append(
            f"| {item.get('task_id')} | {item.get('task_type')} | "
            f"{item.get('diagnostics', {}).get('content_tokens')} | "
            f"{overall.get('window_count')} | "
            f"{fmt(aggregate.get('adjacent_window_distance_mean'))} | "
            f"{fmt(aggregate.get('distance_to_terminal_mean'))} | "
            f"{fmt(aggregate.get('early_late_decay'))} | "
            f"{fmt(aggregate.get('convergence_slope'))} | "
            f"{fmt(aggregate.get('terminal_stability'))} | "
            f"{fmt(aggregate.get('convergence_point_fraction_or_one'))} |"
        )

    lines.extend([
        "",
        "## 字段可测量性",
        "",
        "| 字段 | available | insufficient |",
        "|---|---:|---:|",
    ])
    for dimension in DIMENSIONS:
        statuses = [
            item.get("dimension_convergence", {}).get(dimension, {}).get("measurement_status")
            for item in successful
        ]
        lines.append(
            f"| {dimension} | {statuses.count('available')} | "
            f"{statuses.count('insufficient_fixed_windows')} |"
        )

    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
