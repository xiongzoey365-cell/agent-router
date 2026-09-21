#!/usr/bin/env python3
"""想法一：Qwen3-8B 隐空间语义熵与轨迹漂移探针。

实现依据：Qwen3-8B想法一与想法三实验实现依据.md
本脚本只运行想法一，不生成完整答案，也不评价 L1-L5 标签。
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
import torch.nn.functional as F
import transformers
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from transformers import AutoModelForCausalLM, AutoTokenizer


PROBE_SYSTEM_PROMPT = "请开始分析下面问题的解决思路，不要直接给出最终答案。"
CSV_FIELDS = [
    "task_id",
    "task_type",
    "difficulty_level",
    "probe_text",
    "semantic_entropy_raw",
    "semantic_entropy_normalized",
    "mean_step_distance",
    "direction_change",
    "trajectory_drift_normalized",
    "latent_load_score",
    "runtime_ms",
    "peak_memory_mb",
    "status",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, help="本地 Qwen3-8B 路径或模型名")
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument("--output-dir", default="outputs/method1_latent")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--new-tokens", type=int, default=20)
    parser.add_argument("--analysis-tokens", type=int, default=20, help="仅分析生成序列末尾的 Token 数")
    parser.add_argument("--last-layers", type=int, default=4)
    parser.add_argument("--pca-components", type=int, default=64)
    parser.add_argument("--clusters", type=int, default=8)
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


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    cosine = float(np.dot(left, right) / denominator)
    cosine = float(np.clip(cosine, -1.0, 1.0))
    return float(np.clip((1.0 - cosine) / 2.0, 0.0, 1.0))


def trajectory_metrics(trajectory: np.ndarray) -> tuple[float, float, float]:
    step_distances = [
        cosine_distance(trajectory[index], trajectory[index - 1])
        for index in range(1, len(trajectory))
    ]
    mean_step_distance = float(np.mean(step_distances)) if step_distances else 0.0

    deltas = np.diff(trajectory, axis=0)
    turns = [
        cosine_distance(deltas[index], deltas[index - 1])
        for index in range(1, len(deltas))
    ]
    direction_change = float(np.mean(turns)) if turns else 0.0
    drift = float(np.clip((mean_step_distance + direction_change) / 2.0, 0.0, 1.0))
    return mean_step_distance, direction_change, drift


def collect_trajectory(
    task: dict[str, Any],
    tokenizer: Any,
    model: Any,
    device: torch.device,
    new_tokens: int,
    analysis_tokens: int,
    last_layers: int,
) -> tuple[np.ndarray, str, float, float]:
    messages = [
        {"role": "system", "content": PROBE_SYSTEM_PROMPT},
        {"role": "user", "content": task["prompt"]},
    ]
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    encoded = {key: value.to(device) for key, value in encoded.items()}

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    synchronize(device)
    started = time.perf_counter()

    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = tokenizer.eos_token_id

    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            max_new_tokens=new_tokens,
            min_new_tokens=new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=pad_token_id,
            return_dict_in_generate=True,
        )
        sequence = generated.sequences
        prompt_length = int(encoded["input_ids"].shape[1])
        generated_ids = sequence[:, prompt_length:]
        if int(generated_ids.shape[1]) != new_tokens:
            raise RuntimeError(
                f"期望生成 {new_tokens} Token，实际得到 {generated_ids.shape[1]} Token"
            )

        full_attention_mask = torch.ones_like(sequence, device=device)
        forward = model(
            input_ids=sequence,
            attention_mask=full_attention_mask,
            output_hidden_states=True,
            use_cache=False,
            return_dict=True,
        )

        hidden_states = forward.hidden_states
        if hidden_states is None or len(hidden_states) < last_layers + 1:
            raise RuntimeError("模型没有返回足够的 Hidden States")

        selected_layers = hidden_states[-last_layers:]
        layer_vectors = []
        for layer_state in selected_layers:
            generated_state = layer_state[0, -analysis_tokens:, :].float()
            layer_vectors.append(F.normalize(generated_state, p=2, dim=-1))
        trajectory = torch.stack(layer_vectors, dim=0).mean(dim=0)
        trajectory = F.normalize(trajectory, p=2, dim=-1)
        trajectory_array = trajectory.cpu().numpy().astype(np.float32, copy=False)

    synchronize(device)
    runtime_ms = (time.perf_counter() - started) * 1000.0
    memory_mb = peak_memory_mb(device)
    probe_text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)

    del forward, hidden_states, generated, sequence
    return trajectory_array, probe_text, runtime_ms, memory_mb


def add_semantic_entropy_and_scores(
    results: list[dict[str, Any]],
    trajectories: dict[str, np.ndarray],
    pca_components: int,
    clusters: int,
    seed: int,
) -> dict[str, int]:
    successful = [result for result in results if result["status"] == "success"]
    if not successful:
        return {"pca_components": 0, "clusters": 0}

    lengths: dict[str, int] = {}
    pooled_parts = []
    for result in successful:
        task_id = result["task_id"]
        trajectory = trajectories[task_id]
        lengths[task_id] = len(trajectory)
        pooled_parts.append(trajectory)
    pooled = np.concatenate(pooled_parts, axis=0)

    component_count = min(pca_components, pooled.shape[0] - 1, pooled.shape[1])
    if component_count < 1:
        raise RuntimeError("成功采集的 Hidden State 数量不足以执行 PCA")
    pca = PCA(n_components=component_count, random_state=seed)
    projected = pca.fit_transform(pooled)

    cluster_count = min(clusters, projected.shape[0])
    if cluster_count < 2:
        raise RuntimeError("成功采集的 Hidden State 数量不足以执行聚类")
    kmeans = KMeans(n_clusters=cluster_count, random_state=seed, n_init=10)
    labels = kmeans.fit_predict(projected)

    offset = 0
    for result in successful:
        task_id = result["task_id"]
        count = lengths[task_id]
        task_labels = labels[offset : offset + count]
        offset += count
        frequencies = np.bincount(task_labels, minlength=cluster_count).astype(np.float64)
        probabilities = frequencies[frequencies > 0] / float(count)
        entropy_raw = float(-np.sum(probabilities * np.log(probabilities)))
        entropy_normalized = float(entropy_raw / math.log(cluster_count))
        entropy_normalized = float(np.clip(entropy_normalized, 0.0, 1.0))

        trajectory = trajectories[task_id]
        step_distance, direction_change, drift = trajectory_metrics(trajectory)
        score = float(np.clip(100.0 * (entropy_normalized + drift) / 2.0, 0.0, 100.0))

        result.update(
            {
                "semantic_entropy_raw": entropy_raw,
                "semantic_entropy_normalized": entropy_normalized,
                "mean_step_distance": step_distance,
                "direction_change": direction_change,
                "trajectory_drift_normalized": drift,
                "latent_load_score": score,
            }
        )

    return {"pca_components": component_count, "clusters": cluster_count}


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
    scores = [item["latent_load_score"] for item in successful]

    figure, axis = plt.subplots(figsize=(14, 6))
    axis.bar(task_ids, scores, color="#4472C4")
    axis.set_ylabel("Latent load score (0-100)")
    axis.set_title("Method 1: latent load score by task")
    axis.set_ylim(0, 100)
    axis.tick_params(axis="x", rotation=75)
    figure.tight_layout()
    figure.savefig(output_dir / "scores_bar.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(scores, bins=min(10, max(3, len(scores))), color="#4472C4", edgecolor="white")
    axis.set_xlabel("Latent load score (0-100)")
    axis.set_ylabel("Task count")
    axis.set_title("Method 1 score distribution")
    axis.set_xlim(0, 100)
    figure.tight_layout()
    figure.savefig(output_dir / "scores_histogram.png", dpi=160)
    plt.close(figure)


def write_report(path: Path, config: dict[str, Any], results: list[dict[str, Any]]) -> None:
    successful = [item for item in results if item["status"] == "success"]
    failed = [item for item in results if item["status"] != "success"]
    scores = [float(item["latent_load_score"]) for item in successful]
    runtimes = [float(item["runtime_ms"]) for item in successful]
    memories = [float(item["peak_memory_mb"]) for item in successful]

    lines = [
        "# 想法一实验结果",
        "",
        "> 本报告只展示隐空间探针结果，不评价完整答案，也不与 L1–L5 比较。",
        "",
        "## 实验配置",
        "",
        f"- 模型：`{config['model_path']}`",
        f"- 设备：`{config['device']}`",
        f"- 精度：`{config['dtype']}`",
        f"- 生成 Token：{config['new_tokens']}",
        f"- 分析 Token：生成序列末尾 {config['analysis_tokens']} 个",
        f"- 最后层数：{config['last_layers']}",
        f"- PCA 维度：{config['effective_pca_components']}",
        f"- 聚类数：{config['effective_clusters']}",
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
            "| task_id | task_type | 语义熵 | 轨迹漂移 | LatentLoadScore | 状态 |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in results:
        if item["status"] == "success":
            lines.append(
                f"| {item['task_id']} | {item['task_type']} | "
                f"{item['semantic_entropy_normalized']:.4f} | "
                f"{item['trajectory_drift_normalized']:.4f} | "
                f"{item['latent_load_score']:.4f} | success |"
            )
        else:
            lines.append(f"| {item['task_id']} | {item['task_type']} | - | - | - | error |")

    if failed:
        lines.extend(["", "## 失败记录", ""])
        for item in failed:
            lines.append(f"- `{item['task_id']}`：{item['error']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not 1 <= args.analysis_tokens <= args.new_tokens: raise ValueError("--analysis-tokens 必须位于 1 和 --new-tokens 之间")
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
    ).to(device)
    model.eval()

    results: list[dict[str, Any]] = []
    trajectories: dict[str, np.ndarray] = {}
    for task in tasks:
        base = {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "difficulty_level": task["difficulty_level"],
            "probe_text": "",
            "semantic_entropy_raw": None,
            "semantic_entropy_normalized": None,
            "mean_step_distance": None,
            "direction_change": None,
            "trajectory_drift_normalized": None,
            "latent_load_score": None,
            "runtime_ms": None,
            "peak_memory_mb": None,
            "status": "error",
            "error": "",
        }
        try:
            trajectory, probe_text, runtime_ms, memory_mb = collect_trajectory(
                task=task,
                tokenizer=tokenizer,
                model=model,
                device=device,
                new_tokens=args.new_tokens,
                analysis_tokens=args.analysis_tokens,
                last_layers=args.last_layers,
            )
            trajectories[task["task_id"]] = trajectory
            base.update(
                {
                    "probe_text": probe_text,
                    "runtime_ms": runtime_ms,
                    "peak_memory_mb": memory_mb,
                    "status": "success",
                }
            )
        except Exception as exc:  # 单题失败必须记录并继续
            base["error"] = f"{type(exc).__name__}: {exc}"
            if device.type == "cuda":
                torch.cuda.empty_cache()
        results.append(base)

    effective = add_semantic_entropy_and_scores(
        results=results,
        trajectories=trajectories,
        pca_components=args.pca_components,
        clusters=args.clusters,
        seed=args.seed,
    )

    config = {
        "method": "latent_semantic_entropy_and_trajectory_drift",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": args.model_path,
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "device": str(device),
        "dtype": args.dtype,
        "seed": args.seed,
        "new_tokens": args.new_tokens,
        "analysis_tokens": args.analysis_tokens,
        "last_layers": args.last_layers,
        "requested_pca_components": args.pca_components,
        "effective_pca_components": effective["pca_components"],
        "requested_clusters": args.clusters,
        "effective_clusters": effective["clusters"],
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
