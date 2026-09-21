#!/usr/bin/env python3
"""Qwen3-8B 单轨迹、多检查点硬指标收敛探针。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import random
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

PREREASON_SYSTEM = (
    "你只进行有限预算的预分析，不要给出完整答案。分析题目的关键约束、候选解题路径和仍未解决的障碍。"
    "允许修正思路，但保持紧凑；不要总结成最终答案。"
)
# 每个 checkpoint 都使用完全相同的文本；只比较这段文本对应的内部表示。
FIXED_PROBE_TEXT = "当前已经确定的核心解题方法是："
REVERSAL_PATTERNS = (
    r"\bwait\b", r"\bhowever\b", r"\bactually\b", r"\breconsider\b",
    r"\bnot correct\b", r"\bthat is wrong\b", r"等等", r"但是", r"不过",
    r"重新考虑", r"前面不对", r"不对", r"换一种",
)
CSV_FIELDS = (
    "task_id", "task_type", "difficulty_level", "generated_tokens", "termination_status",
    "terminal_max_distance", "terminal_mean_distance", "last_distance",
    "distance_tail_nonincreasing", "max_lexical_repetition_rate", "max_segment_revisit_rate",
    "loop_suspect", "path_reversal_count", "prereason_runtime_ms", "probe_runtime_ms",
    "peak_memory_mb", "status", "error",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument("--output-dir", default="outputs/checkpoint_convergence")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--checkpoints", default="64,128,192,256")
    parser.add_argument("--window-size", type=int, default=32)
    parser.add_argument("--repeat-ngram-size", type=int, default=4)
    parser.add_argument("--revisit-span", type=int, default=8)
    parser.add_argument("--last-layers", type=int, default=4)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def parse_checkpoints(raw: str, maximum: int) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values or values != sorted(set(values)) or values[0] < 1 or values[-1] > maximum:
        raise ValueError("checkpoints 必须是递增、不重复且不超过 max-new-tokens 的正整数")
    return values


def load_tasks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("输入文件必须包含非空 tasks 数组")
    required = {"task_id", "task_type", "difficulty_level", "prompt"}
    for index, task in enumerate(tasks):
        missing = required.difference(task)
        if missing:
            raise ValueError(f"tasks[{index}] 缺少字段: {sorted(missing)}")
    return tasks


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    cosine = float(np.dot(left, right) / denominator)
    return float(np.clip(1.0 - cosine, 0.0, 2.0))


def lexical_repetition(ids: list[int], n: int) -> float:
    grams = [tuple(ids[index:index + n]) for index in range(max(0, len(ids) - n + 1))]
    if not grams:
        return 0.0
    counts = Counter(grams)
    return float(sum(max(count - 1, 0) for count in counts.values()) / len(grams))


def reversal_count(text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.I)) for pattern in REVERSAL_PATTERNS)


def longest_common_substring(left: list[int], right: list[int]) -> int:
    """Return the longest contiguous equal Token span between two segments."""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for token_left in left:
        current = [0]
        for index, token_right in enumerate(right, 1):
            value = previous[index - 1] + 1 if token_left == token_right else 0
            current.append(value)
            best = max(best, value)
        previous = current
    return best


def segment_revisit_rate(ids: list[int], window_size: int, revisit_span: int) -> tuple[float, int]:
    segments = [ids[start:start + window_size] for start in range(0, len(ids), window_size)]
    if len(segments) < 3:
        return 0.0, 0
    revisits = 0
    maximum = 0
    for index in range(2, len(segments)):
        historical = [longest_common_substring(segments[index], segments[old]) for old in range(index - 1)]
        span = max(historical, default=0)
        maximum = max(maximum, span)
        revisits += span >= revisit_span
    return float(revisits / (len(segments) - 2)), maximum


def build_generation_input(task: dict[str, Any], tokenizer: Any) -> tuple[torch.Tensor, list[int], list[int]]:
    messages = [
        {"role": "system", "content": PREREASON_SYSTEM},
        {"role": "user", "content": task["prompt"]},
    ]
    rendered = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=True,
    )
    base_ids = tokenizer(rendered, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
    probe_ids = tokenizer(FIXED_PROBE_TEXT, add_special_tokens=False)["input_ids"]
    return base_ids, base_ids.tolist(), probe_ids


def generate_trace(model: Any, tokenizer: Any, base_ids: torch.Tensor, device: torch.device,
                   max_tokens: int) -> tuple[list[int], str, float]:
    encoded = {"input_ids": base_ids.unsqueeze(0).to(device)}
    encoded["attention_mask"] = torch.ones_like(encoded["input_ids"])
    started = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(
            **encoded, max_new_tokens=max_tokens, min_new_tokens=max_tokens,
            do_sample=False, temperature=None, top_p=None, top_k=None,
            pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
            return_dict_in_generate=True,
        )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    ids = generated.sequences[0, base_ids.numel():].tolist()
    return ids, tokenizer.decode(ids, skip_special_tokens=True), (time.perf_counter() - started) * 1000.0


def probe_representation(model: Any, base_ids: list[int], prefix_ids: list[int], probe_ids: list[int],
                         device: torch.device, last_layers: int) -> np.ndarray:
    ids = torch.tensor([base_ids + prefix_ids + probe_ids], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(ids)
    with torch.inference_mode():
        output = model(
            input_ids=ids, attention_mask=attention_mask, output_hidden_states=True,
            use_cache=False, return_dict=True,
        )
    hidden_states = output.hidden_states
    if hidden_states is None or len(hidden_states) < last_layers + 1:
        raise RuntimeError("模型没有返回足够的 Hidden States")
    probe_start = len(base_ids) + len(prefix_ids)
    probe_end = probe_start + len(probe_ids)
    layer_vectors = []
    for layer_state in hidden_states[-last_layers:]:
        values = layer_state[0, probe_start:probe_end].float()
        values = F.normalize(values, p=2, dim=-1).mean(dim=0)
        layer_vectors.append(F.normalize(values, p=2, dim=-1))
    vector = F.normalize(torch.stack(layer_vectors).mean(dim=0), p=2, dim=-1)
    return vector.cpu().numpy().astype(np.float32, copy=False)


def checkpoint_metrics(trace_ids: list[int], prefix_text: str, checkpoint: int, window_size: int,
                        repeat_ngram_size: int, revisit_span: int) -> dict[str, Any]:
    prefix_ids = trace_ids[:checkpoint]
    revisit_rate, max_revisit_span = segment_revisit_rate(prefix_ids, window_size, revisit_span)
    return {
        "checkpoint": checkpoint,
        "available_tokens": len(prefix_ids),
        "lexical_repetition_rate": lexical_repetition(prefix_ids, repeat_ngram_size),
        "segment_revisit_rate": revisit_rate,
        "max_revisit_span": max_revisit_span,
        "path_reversal_count": reversal_count(prefix_text),
    }


def derive_summary(checkpoints: list[int], vectors: list[np.ndarray], metrics: list[dict[str, Any]],
                   trace_ids: list[int], max_tokens: int) -> dict[str, Any]:
    distances = [cosine_distance(vectors[index - 1], vectors[index]) for index in range(1, len(vectors))]
    tail = vectors[-3:]
    tail_pairs = [cosine_distance(tail[i], tail[j]) for i in range(len(tail)) for j in range(i + 1, len(tail))]
    tail_distances = distances[-2:] if len(distances) >= 2 else distances
    return {
        "probe_adjacent_distances": distances,
        "probe_terminal_max_distance": max(tail_pairs, default=None),
        "probe_terminal_mean_distance": float(np.mean(tail_pairs)) if tail_pairs else None,
        "probe_last_distance": distances[-1] if distances else None,
        "probe_distance_tail_nonincreasing": bool(
            len(tail_distances) >= 2 and all(left >= right for left, right in zip(tail_distances, tail_distances[1:]))
        ),
        "max_lexical_repetition_rate": max(item["lexical_repetition_rate"] for item in metrics),
        "max_segment_revisit_rate": max(item["segment_revisit_rate"] for item in metrics),
        "max_revisit_span": max(item["max_revisit_span"] for item in metrics),
        "loop_suspect": any(item["max_revisit_span"] >= 8 for item in metrics),
        "path_reversal_count": metrics[-1]["path_reversal_count"],
        "termination_status": "budget_exhausted" if len(trace_ids) >= max_tokens else "ended_early",
    }


def run_task(task: dict[str, Any], model: Any, tokenizer: Any, device: torch.device,
             args: argparse.Namespace, checkpoints: list[int]) -> dict[str, Any]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    base_tensor, base_ids, probe_ids = build_generation_input(task, tokenizer)
    trace_ids, trace_text, prereason_ms = generate_trace(model, tokenizer, base_tensor, device, args.max_new_tokens)
    usable = [checkpoint for checkpoint in checkpoints if checkpoint <= len(trace_ids)]
    if not usable:
        raise RuntimeError(f"预推理只生成 {len(trace_ids)} Token，少于最早检查点 {checkpoints[0]}")
    started_probe = time.perf_counter()
    vectors = [
        probe_representation(model, base_ids, trace_ids[:checkpoint], probe_ids, device, args.last_layers)
        for checkpoint in usable
    ]
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    probe_ms = (time.perf_counter() - started_probe) * 1000.0
    diagnostics = []
    for checkpoint in usable:
        prefix_ids = trace_ids[:checkpoint]
        prefix_text = tokenizer.decode(prefix_ids, skip_special_tokens=True)
        diagnostics.append(checkpoint_metrics(
            trace_ids, prefix_text, checkpoint, args.window_size,
            args.repeat_ngram_size, args.revisit_span,
        ))
    summary = derive_summary(usable, vectors, diagnostics, trace_ids, args.max_new_tokens)
    return {
        "generated_tokens": len(trace_ids), "termination_status": summary.pop("termination_status"),
        "probe_text": FIXED_PROBE_TEXT, "prereason_text": trace_text,
        "checkpoint_metrics": diagnostics, "probe_representations_available": len(vectors),
        **summary, "prereason_runtime_ms": prereason_ms, "probe_runtime_ms": probe_ms,
        "peak_memory_mb": float(torch.cuda.max_memory_allocated(device) / 1024**2) if device.type == "cuda" else 0.0,
    }


def csv_value(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def write_report(path: Path, payload: dict[str, Any]) -> None:
    results = [item for item in payload["results"] if item["status"] == "success"]
    lines = [
        "# 单轨迹、多检查点硬指标报告", "",
        "本报告只记录程序计算的预推理轨迹指标，不使用模型自评，不评价答案正确性。", "",
        "## 汇总", "",
        f"- 成功：{len(results)}/{len(payload['results'])}",
        f"- 预算耗尽：{sum(item['termination_status'] == 'budget_exhausted' for item in results)}",
        f"- 循环嫌疑：{sum(item['loop_suspect'] for item in results)}",
    ]
    if results:
        terminal_distances = [
            item["probe_terminal_max_distance"]
            for item in results
            if item["probe_terminal_max_distance"] is not None
        ]
        lines.extend([
            f"- 末段最大探测距离均值：{statistics.mean(terminal_distances):.6f}" if terminal_distances else "- 末段最大探测距离均值：无可用值",
            f"- 最大4-gram重复率均值：{statistics.mean(item['max_lexical_repetition_rate'] for item in results):.6f}",
        ])
    lines.extend(["", "## 逐题结果", ""])
    for item in payload["results"]:
        lines.extend([
            f"### {item['task_id']}", "",
            f"- 状态：`{item['status']}` / `{item.get('termination_status', '')}`",
            f"- 生成Token：{item.get('generated_tokens', '')}",
            f"- checkpoint间探测距离：{item.get('probe_adjacent_distances', '')}",
            f"- 末段最大探测距离：{item.get('probe_terminal_max_distance', '')}",
            f"- 最大4-gram重复率：{item.get('max_lexical_repetition_rate', '')}",
            f"- 最大片段回访率：{item.get('max_segment_revisit_rate', '')}",
            f"- 循环嫌疑：{item.get('loop_suspect', '')}",
            f"- 错误：{item.get('error', '')}", "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.max_new_tokens < 1 or args.window_size < 1 or args.repeat_ngram_size < 1 or args.revisit_span < 1:
        raise ValueError("Token、窗口和重复检测参数必须为正数")
    checkpoints = parse_checkpoints(args.checkpoints, args.max_new_tokens)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device(args.device)
    dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[args.dtype]
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=args.trust_remote_code)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path, torch_dtype=dtype, trust_remote_code=args.trust_remote_code,
        attn_implementation="sdpa",
    ).to(device).eval()
    results = []
    for task in load_tasks(Path(args.input_file)):
        base = {key: task[key] for key in ("task_id", "task_type", "difficulty_level")}
        try:
            result = {**base, **run_task(task, model, tokenizer, device, args, checkpoints), "status": "success", "error": ""}
        except Exception as exc:
            result = {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(task["task_id"], result["status"], result.get("termination_status", result.get("error", "")))
    payload = {
        "experiment": {
            "method": "single_trajectory_fixed_probe_hard_metrics",
            "created_at": datetime.now(timezone.utc).isoformat(), "model_path": args.model_path,
            "input_file": str(Path(args.input_file).resolve()), "device": str(device), "dtype": args.dtype,
            "seed": args.seed, "max_new_tokens": args.max_new_tokens, "checkpoints": checkpoints,
            "fixed_probe_text": FIXED_PROBE_TEXT, "window_size": args.window_size,
            "repeat_ngram_size": args.repeat_ngram_size, "revisit_span": args.revisit_span,
            "last_layers": args.last_layers, "sampling": False,
            "full_answer_evaluation": False, "label_comparison": False,
            "python_version": platform.python_version(), "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
        }, "results": results,
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in results)
    write_report(output / "report.md", payload)


if __name__ == "__main__":
    main()
