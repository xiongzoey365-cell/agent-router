#!/usr/bin/env python3
"""为独立隐藏状态轨生成 CSV 与 Markdown 报告。"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from common import DIMENSIONS, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    base = "outputs/task_conditioned_capability_sufficiency_no_answer/hidden_state"
    parser.add_argument("--input-file", default=f"{base}/latent_metrics.json")
    parser.add_argument("--csv-file", default=f"{base}/latent_metrics.csv")
    parser.add_argument("--report-file", default=f"{base}/report.md")
    return parser.parse_args()


def fmt(value: Any) -> str:
    return "NA" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)


def main() -> None:
    args = parse_args()
    payload = read_json(Path(args.input_file))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("输入文件必须包含 results 数组")

    rows = []
    for item in results:
        fields = item.get("dimension_latent_load", {})
        row = {
            "task_id": item.get("task_id"),
            "task_type": item.get("task_type"),
            "status": item.get("status"),
            "available_count": len(item.get("available_dimensions", [])),
            "overall_latent_load_proxy": item.get("overall_latent_load_proxy"),
        }
        for dimension in DIMENSIONS:
            field = fields.get(dimension) if isinstance(fields.get(dimension), dict) else {}
            row[f"{dimension}_status"] = field.get("measurement_status")
            row[f"{dimension}_tokens"] = field.get("token_count")
            row[f"{dimension}_latent_load"] = field.get("latent_load_proxy")
        rows.append(row)

    csv_path = Path(args.csv_file)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]) if rows else ["task_id", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)

    successful = [item for item in results if item.get("status") == "success"]
    lines = [
        "# 最小结构化证据 Hidden-State 轨报告",
        "",
        "> 本报告与 LLM-Judge 轨完全独立。latent load 仅为未校准的隐藏状态变化代理，不是能力充分度、答案正确率或客观难度。",
        "",
        "## 概况",
        "",
        f"- 总任务数：{len(results)}",
        f"- 成功提取：{len(successful)}",
        "- 最终答案：未生成",
        "- Judge 输出：未读取",
        "- 两轨融合：未进行",
        "",
        "## 字段可测量性与潜在负荷",
        "",
        "| 字段 | available | empty | too_short | mean | min | max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dimension in DIMENSIONS:
        statuses = Counter(
            item.get("dimension_latent_load", {}).get(dimension, {}).get("measurement_status")
            for item in successful
        )
        values = [
            item["dimension_latent_load"][dimension]["latent_load_proxy"]
            for item in successful
            if item.get("dimension_latent_load", {}).get(dimension, {}).get("latent_load_proxy")
            is not None
        ]
        lines.append(
            f"| {dimension} | {statuses.get('available', 0)} | "
            f"{statuses.get('empty_evidence', 0)} | {statuses.get('too_short', 0)} | "
            f"{fmt(statistics.fmean(values) if values else None)} | "
            f"{fmt(min(values) if values else None)} | "
            f"{fmt(max(values) if values else None)} |"
        )

    lines.extend([
        "",
        "## 逐题结果",
        "",
        "| task_id | type | available fields | overall latent load |",
        "|---|---|---:|---:|",
    ])
    for item in successful:
        lines.append(
            f"| {item.get('task_id')} | {item.get('task_type')} | "
            f"{len(item.get('available_dimensions', []))} | "
            f"{fmt(item.get('overall_latent_load_proxy'))} |"
        )

    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
