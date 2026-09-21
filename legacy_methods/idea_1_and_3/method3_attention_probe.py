#!/usr/bin/env python3
"""想法三：Qwen3-8B Prefill 注意力拓扑探针。

实现依据：Qwen3-8B想法一与想法三实验实现依据.md
本脚本只运行想法三，不生成任何新 Token，也不评价 L1-L5 标签。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


CSV_FIELDS = [
    "task_id",
    "task_type",
    "difficulty_level",
    "prompt_tokens",
    "user_tokens",
    "attention_entropy_normalized",
    "top10_attention_concentration",
    "graph_density_threshold_01",
    "cycle_count",
    "attention_load_score",
    "runtime_ms",
    "peak_memory_mb",
    "status",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, help="本地 Qwen3-8B 路径或模型名")
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument("--output-dir", default="outputs/method3_attention")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--last-layers", type=int, default=2)
    parser.add_argument("--top-fraction", type=float, default=0.10)
    parser.add_argument("--edge-threshold", type=float, default=0.10)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def load_tasks(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("输入文件必须包含非空 tasks 数组")
    required = {"task_id", "task_type", "difficulty_level", "prompt"}
    for index, task in enumerate(tasks):
        missing = required.difference(task)
        if missing:
            raise ValueError(f"tasks[{index}] 缺少字段: {sorted(missing)}")
    return tasks


def resolve_dtype(name: str) -> torch.dtype:
    return {
        "bf16": torch.bfloat16,
        "fp16": torch.float16,
        "fp32": torch.float32,
    }[name]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def peak_memory_mb(device: torch.device) -> float:
    if device.type != "cuda":
        return 0.0
    return float(torch.cuda.max_memory_allocated(device) / (1024**2))


def render_and_locate_user_tokens(
    tokenizer: Any, prompt: str, device: torch.device
) -> tuple[dict[str, torch.Tensor], list[int], str]:
    if not getattr(tokenizer, "is_fast", False):
        raise RuntimeError("想法三需要 fast tokenizer 的 offset_mapping 来定位用户 Token")

    messages = [{"role": "user", "content": prompt}]
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    character_start = rendered.rfind(prompt)
    if character_start < 0:
        raise RuntimeError("无法在 Chat Template 渲染结果中定位原始 prompt")
    character_end = character_start + len(prompt)

    encoded = tokenizer(
        rendered,
        return_tensors="pt",
        return_offsets_mapping=True,
        add_special_tokens=False,
    )
    offsets = encoded.pop("offset_mapping")[0].tolist()
    user_positions = [
        index
        for index, (start, end) in enumerate(offsets)
        if end > start and start < character_end and end > character_start
    ]
    if len(user_positions) < 2:
        raise RuntimeError(f"有效用户 Token 数不足: {len(user_positions)}")

    model_inputs = {
        key: value.to(device)
        for key, value in encoded.items()
        if key in {"input_ids", "attention_mask"}
    }
    return model_inputs, user_positions, rendered


def normalized_rows_for_layer(
    layer_attention: torch.Tensor, user_positions: list[int]
) -> list[torch.Tensor]:
    """返回每个用户 Query 对此前用户 Key 的逐 Head 归一化分布。"""
    rows: list[torch.Tensor] = []
    for local_query, absolute_query in enumerate(user_positions):
        absolute_keys = user_positions[: local_query + 1]
        weights = layer_attention[0, :, absolute_query, absolute_keys].float()
        denominator = weights.sum(dim=-1, keepdim=True).clamp_min(1e-12)
        rows.append(weights / denominator)
    return rows


def attention_statistics(
    selected_attentions: tuple[torch.Tensor, ...],
    user_positions: list[int],
    top_fraction: float,
    edge_threshold: float,
) -> tuple[float, float, float, int]:
    entropy_values: list[float] = []
    concentration_values: list[float] = []

    for layer_attention in selected_attentions:
        rows = normalized_rows_for_layer(layer_attention, user_positions)
        for probabilities in rows:
            key_count = int(probabilities.shape[-1])
            if key_count <= 1:
                continue
            entropy_per_head = -(
                probabilities * probabilities.clamp_min(1e-12).log()
            ).sum(dim=-1) / math.log(key_count)
            top_count = max(1, math.ceil(key_count * top_fraction))
            concentration_per_head = probabilities.topk(top_count, dim=-1).values.sum(dim=-1)
            entropy_values.extend(entropy_per_head.detach().cpu().tolist())
            concentration_values.extend(concentration_per_head.detach().cpu().tolist())

    if not entropy_values or not concentration_values:
        raise RuntimeError("没有得到可计算的注意力分布")
    entropy = float(np.clip(np.mean(entropy_values), 0.0, 1.0))
    concentration = float(np.clip(np.mean(concentration_values), 0.0, 1.0))

    stacked = torch.stack([attention.float() for attention in selected_attentions], dim=0)
    aggregated = stacked.mean(dim=(0, 2))[0]
    edge_count = 0
    possible_edges = 0
    for local_query, absolute_query in enumerate(user_positions):
        if local_query == 0:
            continue
        previous_absolute_keys = user_positions[:local_query]
        all_absolute_keys = user_positions[: local_query + 1]
        row = aggregated[absolute_query, all_absolute_keys]
        row = row / row.sum().clamp_min(1e-12)
        previous_weights = row[: len(previous_absolute_keys)]
        edge_count += int((previous_weights > edge_threshold).sum().item())
        possible_edges += len(previous_absolute_keys)
    graph_density = float(edge_count / possible_edges) if possible_edges else 0.0

    # 排除自环后，因果注意力边只能从当前 Token 指向更早 Token，因此不存在有向环。
    cycle_count = 0
    return entropy, concentration, graph_density, cycle_count


def run_probe(
    task: dict[str, Any],
    tokenizer: Any,
    model: Any,
    device: torch.device,
    last_layers: int,
    top_fraction: float,
    edge_threshold: float,
) -> dict[str, Any]:
    model_inputs, user_positions, _ = render_and_locate_user_tokens(
        tokenizer, task["prompt"], device
    )
    prompt_tokens = int(model_inputs["input_ids"].shape[1])

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    synchronize(device)
    started = time.perf_counter()
    with torch.inference_mode():
        outputs = model(
            **model_inputs,
            output_attentions=True,
            use_cache=False,
            return_dict=True,
        )
        attentions = outputs.attentions
        if attentions is None or len(attentions) < last_layers:
            raise RuntimeError("模型没有返回足够的 Attention Matrix")
        selected = tuple(attentions[-last_layers:])
        if any(attention is None for attention in selected):
            raise RuntimeError("Attention 返回值包含 None，请确认使用 eager attention")
        entropy, concentration, density, cycle_count = attention_statistics(
            selected_attentions=selected,
            user_positions=user_positions,
            top_fraction=top_fraction,
            edge_threshold=edge_threshold,
        )
        score = float(np.clip(100.0 * (entropy + (1.0 - concentration)) / 2.0, 0.0, 100.0))

    synchronize(device)
    runtime_ms = (time.perf_counter() - started) * 1000.0
    memory_mb = peak_memory_mb(device)
    del outputs, attentions, selected
    return {
        "prompt_tokens": prompt_tokens,
        "user_tokens": len(user_positions),
        "attention_entropy_normalized": entropy,
        "top10_attention_concentration": concentration,
        "graph_density_threshold_01": density,
        "cycle_count": cycle_count,
        "attention_load_score": score,
        "runtime_ms": runtime_ms,
        "peak_memory_mb": memory_mb,
    }


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def create_plots(output_dir: Path, results: list[dict[str, Any]]) -> None:
    successful = [item for item in results if item["status"] == "success"]
    if not successful:
        return
    task_ids = [item["task_id"] for item in successful]
    scores = [item["attention_load_score"] for item in successful]

    figure, axis = plt.subplots(figsize=(14, 6))
    axis.bar(task_ids, scores, color="#70AD47")
    axis.set_ylabel("Attention load score (0-100)")
    axis.set_title("Method 3: attention load score by task")
    axis.set_ylim(0, 100)
    axis.tick_params(axis="x", rotation=75)
    figure.tight_layout()
    figure.savefig(output_dir / "scores_bar.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(scores, bins=min(10, max(3, len(scores))), color="#70AD47", edgecolor="white")
    axis.set_xlabel("Attention load score (0-100)")
    axis.set_ylabel("Task count")
    axis.set_title("Method 3 score distribution")
    axis.set_xlim(0, 100)
    figure.tight_layout()
    figure.savefig(output_dir / "scores_histogram.png", dpi=160)
    plt.close(figure)


def write_report(path: Path, config: dict[str, Any], results: list[dict[str, Any]]) -> None:
    successful = [item for item in results if item["status"] == "success"]
    failed = [item for item in results if item["status"] != "success"]
    scores = [float(item["attention_load_score"]) for item in successful]
    runtimes = [float(item["runtime_ms"]) for item in successful]
    memories = [float(item["peak_memory_mb"]) for item in successful]

    lines = [
        "# 想法三实验结果",
        "",
        "> 本报告只展示注意力拓扑探针结果，不生成完整答案，也不与 L1–L5 比较。",
        "",
        "## 实验配置",
        "",
        f"- 模型：`{config['model_path']}`",
        f"- 设备：`{config['device']}`",
        f"- 精度：`{config['dtype']}`",
        f"- 最后层数：{config['last_layers']}",
        f"- Top 比例：{config['top_fraction']}",
        f"- 图边阈值：{config['edge_threshold']}",
        f"- 成功/总数：{len(successful)}/{len(results)}",
        "",
        "## 汇总",
        "",
    ]
    if scores:
        lines.extend(
            [
                f"- 最小分数：{min(scores):.4f}",
                f"- 最大分数：{max(scores):.4f}",
                f"- 平均分数：{statistics.fmean(scores):.4f}",
                f"- 中位数：{statistics.median(scores):.4f}",
                f"- 平均耗时：{statistics.fmean(runtimes):.2f} ms",
                f"- 最大峰值显存：{max(memories):.2f} MB",
            ]
        )
    else:
        lines.append("- 没有成功样本。")

    lines.extend(
        [
            "",
            "## 逐题结果",
            "",
            "| task_id | task_type | 注意力熵 | Top10%集中度 | 图密度 | AttentionLoadScore | 状态 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in results:
        if item["status"] == "success":
            lines.append(
                f"| {item['task_id']} | {item['task_type']} | "
                f"{item['attention_entropy_normalized']:.4f} | "
                f"{item['top10_attention_concentration']:.4f} | "
                f"{item['graph_density_threshold_01']:.4f} | "
                f"{item['attention_load_score']:.4f} | success |"
            )
        else:
            lines.append(f"| {item['task_id']} | {item['task_type']} | - | - | - | - | error |")

    if failed:
        lines.extend(["", "## 失败记录", ""])
        for item in failed:
            lines.append(f"- `{item['task_id']}`：{item['error']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not 0.0 < args.top_fraction <= 1.0:
        raise ValueError("--top-fraction 必须位于 (0, 1]")
    if not 0.0 <= args.edge_threshold <= 1.0:
        raise ValueError("--edge-threshold 必须位于 [0, 1]")
    set_seed(args.seed)

    input_path = Path(args.input_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(input_path)

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求使用 CUDA，但当前环境不可用")
    dtype = resolve_dtype(args.dtype)

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=args.trust_remote_code,
        use_fast=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=dtype,
        trust_remote_code=args.trust_remote_code,
        low_cpu_mem_usage=True,
        attn_implementation="eager",
    ).to(device)
    model.eval()

    results: list[dict[str, Any]] = []
    for task in tasks:
        base = {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "difficulty_level": task["difficulty_level"],
            "prompt_tokens": None,
            "user_tokens": None,
            "attention_entropy_normalized": None,
            "top10_attention_concentration": None,
            "graph_density_threshold_01": None,
            "cycle_count": None,
            "attention_load_score": None,
            "runtime_ms": None,
            "peak_memory_mb": None,
            "status": "error",
            "error": "",
        }
        try:
            metrics = run_probe(
                task=task,
                tokenizer=tokenizer,
                model=model,
                device=device,
                last_layers=args.last_layers,
                top_fraction=args.top_fraction,
                edge_threshold=args.edge_threshold,
            )
            base.update(metrics)
            base["status"] = "success"
        except Exception as exc:  # 单题失败必须记录并继续
            base["error"] = f"{type(exc).__name__}: {exc}"
            if device.type == "cuda":
                torch.cuda.empty_cache()
        results.append(base)

    config = {
        "method": "prefill_attention_topology",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": args.model_path,
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "device": str(device),
        "dtype": args.dtype,
        "seed": args.seed,
        "last_layers": args.last_layers,
        "top_fraction": args.top_fraction,
        "edge_threshold": args.edge_threshold,
        "attention_implementation": "eager",
        "compare_with_difficulty_labels": False,
        "evaluate_full_answers": False,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
    }

    with (output_dir / "results.json").open("w", encoding="utf-8") as handle:
        json.dump({"experiment": config, "results": results}, handle, ensure_ascii=False, indent=2)
    write_csv(output_dir / "results.csv", results)
    write_report(output_dir / "report.md", config, results)
    create_plots(output_dir, results)


if __name__ == "__main__":
    main()
