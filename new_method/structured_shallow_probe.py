#!/usr/bin/env python3
"""Qwen3-8B 结构化浅推理与 Hidden State 动态趋势探针。"""

from __future__ import annotations

import argparse
import csv
import json
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

SYSTEM_PROMPT = (
    "你只做一份简短的结构化预分析，不要给出完整答案、完整代码或完整证明，也不要评价难度和置信度。"
    "必须严格输出三行，格式如下：\n"
    "关键约束：列出必须满足的条件、输入限制和评价要求。\n"
    "核心方案：给出准备采用的方法和2到4个关键步骤，不展开完整答案。\n"
    "待补环节：指出仍需推导、验证或实现的关键部分；如果没有，写无。"
)
FIXED_PROBE_TEXT = "当前核心解题方案是："
SECTION_NAMES = ("关键约束", "核心方案", "待补环节")
REVERSAL_PATTERNS = (
    r"\bwait\b", r"\bhowever\b", r"\bactually\b", r"\breconsider\b",
    r"\bnot correct\b", r"\bthat is wrong\b", r"等等", r"但是", r"不过",
    r"重新考虑", r"前面不对", r"不对", r"换一种",
)
CSV_FIELDS = (
    "task_id", "task_type", "difficulty_level", "generated_tokens", "termination_status",
    "structure_completeness", "pending_is_empty", "terminal_probe_distance",
    "probe_early_distance", "probe_late_distance", "probe_decay_score",
    "natural_early_distance", "natural_late_distance", "natural_decay_score",
    "lexical_repetition_rate", "segment_revisit_rate", "path_reversal_count",
    "solveability_proxy_score", "status", "error",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument("--output-dir", default="outputs/structured_shallow_probe")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--window-size", type=int, default=32)
    parser.add_argument("--checkpoints", default="32,64,96,128,160,192,224,256,320,384")
    parser.add_argument("--last-layers", type=int, default=4)
    parser.add_argument("--repeat-ngram-size", type=int, default=4)
    parser.add_argument("--revisit-span", type=int, default=8)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def parse_checkpoints(raw: str, maximum: int) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values or values != sorted(set(values)) or values[0] < 1 or values[-1] > maximum:
        raise ValueError("checkpoints必须递增、不重复且不超过max-new-tokens")
    return values


def load_tasks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("输入文件必须包含非空tasks数组")
    required = {"task_id", "task_type", "difficulty_level", "prompt"}
    for index, task in enumerate(tasks):
        missing = required.difference(task)
        if missing:
            raise ValueError(f"tasks[{index}]缺少字段: {sorted(missing)}")
    return tasks


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    return float(np.clip(1.0 - np.dot(left, right) / denominator, 0.0, 2.0))


def lexical_repetition(ids: list[int], n: int) -> float:
    grams = [tuple(ids[index:index + n]) for index in range(max(0, len(ids) - n + 1))]
    if not grams:
        return 0.0
    counts = Counter(grams)
    return float(sum(max(count - 1, 0) for count in counts.values()) / len(grams))


def longest_common_substring(left: list[int], right: list[int]) -> int:
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


def revisit_metrics(ids: list[int], window_size: int, revisit_span: int) -> tuple[float, int]:
    segments = [ids[start:start + window_size] for start in range(0, len(ids), window_size)]
    if len(segments) < 3:
        return 0.0, 0
    hits = 0
    maximum = 0
    for index in range(2, len(segments)):
        span = max((longest_common_substring(segments[index], segments[j]) for j in range(index - 1)), default=0)
        maximum = max(maximum, span)
        hits += span >= revisit_span
    return hits / (len(segments) - 2), maximum


def reversal_count(text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.I)) for pattern in REVERSAL_PATTERNS)


def parse_sections(text: str) -> dict[str, Any]:
    positions = []
    for name in SECTION_NAMES:
        match = re.search(rf"(?:^|\n)\s*{re.escape(name)}\s*[:：]\s*", text, flags=re.I)
        if match:
            positions.append((match.start(), match.end(), name))
    positions.sort()
    sections = {name: "" for name in SECTION_NAMES}
    for index, (_, content_start, name) in enumerate(positions):
        content_end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        sections[name] = text[content_start:content_end].strip()
    nonempty = sum(bool(value) for value in sections.values())
    pending = sections["待补环节"].strip().lower()
    pending_is_empty = pending in {"无", "无。", "none", "nothing", "n/a"}
    return {
        "sections": sections,
        "structure_completeness": nonempty / len(SECTION_NAMES),
        "pending_is_empty": pending_is_empty,
    }


def build_base(task: dict[str, Any], tokenizer: Any) -> tuple[list[int], list[int]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task["prompt"]}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    base_ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
    probe_ids = tokenizer(FIXED_PROBE_TEXT, add_special_tokens=False)["input_ids"]
    return base_ids, probe_ids


def generate_trace(model: Any, tokenizer: Any, base_ids: list[int], device: torch.device,
                   max_tokens: int) -> tuple[list[int], str, float]:
    encoded = {"input_ids": torch.tensor([base_ids], dtype=torch.long, device=device)}
    encoded["attention_mask"] = torch.ones_like(encoded["input_ids"])
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **encoded, max_new_tokens=max_tokens, do_sample=False,
            temperature=None, top_p=None, top_k=None,
            pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
            return_dict_in_generate=True,
        )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    ids = output.sequences[0, len(base_ids):].tolist()
    return ids, tokenizer.decode(ids, skip_special_tokens=True), (time.perf_counter() - started) * 1000.0


def hidden_vector(model: Any, base_ids: list[int], prefix_ids: list[int], probe_ids: list[int],
                  device: torch.device, last_layers: int) -> np.ndarray:
    ids = torch.tensor([base_ids + prefix_ids + probe_ids], dtype=torch.long, device=device)
    with torch.inference_mode():
        output = model(
            input_ids=ids, attention_mask=torch.ones_like(ids), output_hidden_states=True,
            use_cache=False, return_dict=True,
        )
    states = output.hidden_states
    if states is None or len(states) < last_layers + 1:
        raise RuntimeError("模型没有返回足够的Hidden States")
    start = len(base_ids) + len(prefix_ids)
    end = start + len(probe_ids)
    layers = []
    for state in states[-last_layers:]:
        values = F.normalize(state[0, start:end].float(), p=2, dim=-1).mean(dim=0)
        layers.append(F.normalize(values, p=2, dim=-1))
    return F.normalize(torch.stack(layers).mean(dim=0), p=2, dim=-1).cpu().numpy().astype(np.float32)


def natural_window_vectors(model: Any, base_ids: list[int], trace_ids: list[int], device: torch.device,
                           window_size: int, last_layers: int) -> list[np.ndarray]:
    ids = torch.tensor([base_ids + trace_ids], dtype=torch.long, device=device)
    with torch.inference_mode():
        output = model(input_ids=ids, attention_mask=torch.ones_like(ids), output_hidden_states=True,
                       use_cache=False, return_dict=True)
    states = output.hidden_states
    vectors = []
    for start in range(0, len(trace_ids), window_size):
        end = min(start + window_size, len(trace_ids))
        layer_vectors = []
        for state in states[-last_layers:]:
            values = F.normalize(state[0, len(base_ids) + start:len(base_ids) + end].float(), p=2, dim=-1).mean(dim=0)
            layer_vectors.append(F.normalize(values, p=2, dim=-1))
        vectors.append(F.normalize(torch.stack(layer_vectors).mean(dim=0), p=2, dim=-1).cpu().numpy().astype(np.float32))
    return vectors


def distance_summary(vectors: list[np.ndarray]) -> dict[str, Any]:
    distances = [cosine_distance(vectors[i - 1], vectors[i]) for i in range(1, len(vectors))]
    half = max(1, len(distances) // 2)
    early = float(np.mean(distances[:half])) if distances else 0.0
    late = float(np.mean(distances[half:])) if distances[half:] else early
    return {
        "distances": distances, "early_distance": early, "late_distance": late,
        "decay_score": float(np.clip((early - late) / (early + 1e-12), 0.0, 1.0)),
    }


def run_task(task: dict[str, Any], model: Any, tokenizer: Any, device: torch.device,
             args: argparse.Namespace, checkpoints: list[int]) -> dict[str, Any]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    base_ids, probe_ids = build_base(task, tokenizer)
    trace_ids, trace_text, prereason_ms = generate_trace(model, tokenizer, base_ids, device, args.max_new_tokens)
    usable = [checkpoint for checkpoint in checkpoints if checkpoint <= len(trace_ids)]
    if not usable:
        # 结构化浅推理允许自然提前结束；实际结束位置本身作为一个可用检查点。
        usable = [len(trace_ids)]
    started = time.perf_counter()
    probe_vectors = [hidden_vector(model, base_ids, trace_ids[:checkpoint], probe_ids, device, args.last_layers) for checkpoint in usable]
    natural_vectors = natural_window_vectors(model, base_ids, trace_ids, device, args.window_size, args.last_layers)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    probe_ms = (time.perf_counter() - started) * 1000.0
    probe_summary = distance_summary(probe_vectors)
    natural_summary = distance_summary(natural_vectors)
    diagnostics = []
    for checkpoint in usable:
        prefix = trace_ids[:checkpoint]
        prefix_text = tokenizer.decode(prefix, skip_special_tokens=True)
        revisit, max_span = revisit_metrics(prefix, args.window_size, args.revisit_span)
        diagnostics.append({
            "checkpoint": checkpoint,
            "available_tokens": len(prefix),
            "lexical_repetition_rate": lexical_repetition(prefix, args.repeat_ngram_size),
            "segment_revisit_rate": revisit,
            "max_revisit_span": max_span,
            "path_reversal_count": reversal_count(prefix_text),
        })
    parsed = parse_sections(trace_text)
    final_diag = diagnostics[-1]
    return {
        "generated_tokens": len(trace_ids), "termination_status": "budget_exhausted" if len(trace_ids) >= args.max_new_tokens else "ended_early",
        "prereason_text": trace_text, "parsed_sections": parsed["sections"],
        "structure_completeness": parsed["structure_completeness"], "pending_is_empty": parsed["pending_is_empty"],
        "checkpoints": usable, "checkpoint_diagnostics": diagnostics,
        "probe_adjacent_distances": probe_summary["distances"], "probe_early_distance": probe_summary["early_distance"],
        "probe_late_distance": probe_summary["late_distance"], "probe_decay_score": probe_summary["decay_score"],
        "terminal_probe_distance": max(probe_summary["distances"][-2:], default=None),
        "natural_adjacent_distances": natural_summary["distances"], "natural_early_distance": natural_summary["early_distance"],
        "natural_late_distance": natural_summary["late_distance"], "natural_decay_score": natural_summary["decay_score"],
        "lexical_repetition_rate": final_diag["lexical_repetition_rate"],
        "segment_revisit_rate": final_diag["segment_revisit_rate"],
        "path_reversal_count": final_diag["path_reversal_count"],
        "prereason_runtime_ms": prereason_ms, "probe_runtime_ms": probe_ms,
        "peak_memory_mb": float(torch.cuda.max_memory_allocated(device) / 1024**2) if device.type == "cuda" else 0.0,
    }


def add_proxy_scores(results: list[dict[str, Any]]) -> None:
    successful = [result for result in results if result["status"] == "success"]
    if not successful:
        return
    observed_distances = [
        result["terminal_probe_distance"]
        for result in successful
        if result["terminal_probe_distance"] is not None
    ]
    q90 = float(np.percentile(observed_distances, 90)) if observed_distances else 0.0
    for result in successful:
        stable = (
            0.5 if result["terminal_probe_distance"] is None
            else 1.0 - min(1.0, result["terminal_probe_distance"] / (q90 + 1e-12))
        )
        repeat_safe = 1.0 - max(result["lexical_repetition_rate"], result["segment_revisit_rate"])
        score = 100.0 * (
            0.30 * stable + 0.20 * result["probe_decay_score"]
            + 0.20 * repeat_safe + 0.30 * result["structure_completeness"]
        )
        result.update({
            "stable_subscore": stable, "decay_subscore": result["probe_decay_score"],
            "repeat_safety_subscore": repeat_safe, "structure_subscore": result["structure_completeness"],
            "solveability_proxy_score": float(np.clip(score, 0.0, 100.0)),
        })


def csv_value(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def write_report(path: Path, payload: dict[str, Any]) -> None:
    successful = [item for item in payload["results"] if item["status"] == "success"]
    lines = [
        "# 结构化浅推理可解性探针报告", "",
        "分数是批次内代理分数，不是成功概率，不评价完整答案。", "", "## 汇总", "",
        f"- 成功：{len(successful)}/{len(payload['results'])}",
    ]
    if successful:
        scores = [item["solveability_proxy_score"] for item in successful]
        lines.extend([
            f"- 代理分数：均值{statistics.mean(scores):.2f}，最小{min(scores):.2f}，最大{max(scores):.2f}",
            f"- 结构完整度均值：{statistics.mean(item['structure_completeness'] for item in successful):.3f}",
            f"- 探测变化衰减均值：{statistics.mean(item['probe_decay_score'] for item in successful):.3f}",
        ])
    lines.extend(["", "## 逐题结果", ""])
    for item in payload["results"]:
        lines.extend([
            f"### {item['task_id']}", "",
            f"- 状态：`{item['status']}` / `{item.get('termination_status', '')}`",
            f"- 代理分数：{item.get('solveability_proxy_score', '')}",
            f"- 结构完整度：{item.get('structure_completeness', '')}",
            f"- 探测距离：{item.get('probe_adjacent_distances', '')}",
            f"- 探测衰减：{item.get('probe_decay_score', '')}",
            f"- 重复率：{item.get('lexical_repetition_rate', '')}",
            f"- 回访率：{item.get('segment_revisit_rate', '')}",
            f"- 错误：{item.get('error', '')}", "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
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
        print(task["task_id"], result["status"], result.get("generated_tokens", ""))
    add_proxy_scores(results)
    payload = {
        "experiment": {
            "method": "structured_shallow_reasoning_hidden_state_trend",
            "created_at": datetime.now(timezone.utc).isoformat(), "model_path": args.model_path,
            "input_file": str(Path(args.input_file).resolve()), "device": str(device), "dtype": args.dtype,
            "seed": args.seed, "max_new_tokens": args.max_new_tokens, "checkpoints": checkpoints,
            "window_size": args.window_size, "fixed_probe_text": FIXED_PROBE_TEXT,
            "last_layers": args.last_layers, "repeat_ngram_size": args.repeat_ngram_size,
            "revisit_span": args.revisit_span, "sampling": False, "thinking": False,
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
