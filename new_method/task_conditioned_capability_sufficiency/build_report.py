#!/usr/bin/env python3
"""把六维充分度结果导出为 CSV 与简洁 Markdown 报告。"""

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
    parser.add_argument("--input-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/sufficiency_results.json")
    parser.add_argument("--csv-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/sufficiency_results.csv")
    parser.add_argument("--report-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/report.md")
    return parser.parse_args()


def fmt(value: Any) -> str:
    return "NA" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def main() -> None:
    args = parse_args()
    payload = read_json(Path(args.input_file))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("输入文件必须包含 results 数组")
    rows = []
    for item in results:
        scores = item.get("capability_sufficiency", {})
        row = {"model": item.get("model"), "task_id": item.get("task_id"), "task_type": item.get("task_type"), "status": item.get("status")}
        row.update({dimension: scores.get(dimension) for dimension in DIMENSIONS})
        row.update({"observable_count": len(item.get("observable_dimensions", [])), "overall_sufficiency": item.get("overall_sufficiency"), "relative_difficulty": item.get("relative_difficulty"), "bottlenecks": ";".join((item.get("bottleneck") or {}).get("dimensions", []))})
        rows.append(row)
    csv_path = Path(args.csv_file); csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["task_id"]); writer.writeheader(); writer.writerows(rows)
    good = [item for item in results if item.get("status") == "success"]
    lines = ["# Task-conditioned Capability Sufficiency 实验报告", "", "> 分数描述模型与具体任务交互时暴露出的能力充分度，不是模型静态能力或题目客观难度。被测模型未生成最终答案；本轨只评价最小结构化证据。", "", "## 概况", "", f"- 任务数：{len(results)}", f"- 成功评分：{len(good)}", "- 训练：无", "- Hidden State：未使用", "- 聚合：仅对非 null 维度做无权平均", "", "## 各维度可观察性与分布", "", "| 维度 | 可观察题数 | 均值 | 最小 | 最大 |", "|---|---:|---:|---:|---:|"]
    for dimension in DIMENSIONS:
        values = [item["capability_sufficiency"][dimension] for item in good if item.get("capability_sufficiency", {}).get(dimension) is not None]
        lines.append(f"| {dimension} | {len(values)} | {fmt(statistics.fmean(values) if values else None)} | {fmt(min(values) if values else None)} | {fmt(max(values) if values else None)} |")
    bottlenecks = Counter(name for item in good for name in (item.get("bottleneck") or {}).get("dimensions", []))
    lines.extend(["", "## 瓶颈分布", "", f"{dict(bottlenecks)}", "", "## 逐题结果", "", "| task_id | type | observable | overall | relative difficulty | bottleneck |", "|---|---|---:|---:|---:|---|"])
    for item in good:
        lines.append(f"| {item.get('task_id')} | {item.get('task_type')} | {len(item.get('observable_dimensions', []))} | {fmt(item.get('overall_sufficiency'))} | {fmt(item.get('relative_difficulty'))} | {', '.join((item.get('bottleneck') or {}).get('dimensions', []))} |")
    report_path = Path(args.report_file); report_path.parent.mkdir(parents=True, exist_ok=True); report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
