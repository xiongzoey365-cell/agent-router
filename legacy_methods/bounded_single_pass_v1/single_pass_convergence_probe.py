#!/usr/bin/env python3
"""Qwen3-8B 单次、预算受限的预推理收敛性探针。"""

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
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

SYSTEM_PROMPT = (
    "你正在进行一次有限预算的预分析，而不是完整作答。请只分析关键约束、候选解题路径和仍未解决的障碍，"
    "不要给出完整答案。若解题路径已经明确且不存在关键障碍，请在末尾单独输出 <READY> 并立即停止。"
    "若发现题目矛盾、信息不足，或在预算内无法确定可靠路径，请在末尾单独输出 <UNRESOLVED> 并立即停止。"
    "不要在其他位置使用这两个标记。"
)
MARKERS = ("<READY>", "<UNRESOLVED>")
REVERSAL_PATTERNS = (
    r"\bwait\b", r"\bhowever\b", r"\bactually\b", r"\breconsider\b",
    r"\bnot correct\b", r"\bthat is wrong\b", r"等等", r"但是", r"不过",
    r"重新考虑", r"前面不对", r"不对", r"换一种",
)
CSV_FIELDS = (
    "task_id", "task_type", "difficulty_level", "termination_status",
    "convergence_tokens", "window_count", "terminal_stability",
    "mean_adjacent_window_distance", "semantic_revisit_rate",
    "lexical_repetition_rate", "path_reversal_count", "probe_text",
    "runtime_ms", "peak_memory_mb", "status", "error",
)


class StopAfterTokenSequence(StoppingCriteria):
    def __init__(self, sequences: list[list[int]]) -> None:
        self.sequences = [torch.tensor(x, dtype=torch.long) for x in sequences]

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs: Any) -> bool:
        row = input_ids[0]
        return any(len(row) >= len(seq) and torch.equal(row[-len(seq):].cpu(), seq) for seq in self.sequences)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-path", required=True)
    p.add_argument("--input-file", default="测试数据.txt")
    p.add_argument("--output-dir", default="outputs/single_pass_convergence")
    p.add_argument("--device", default="cuda")
    p.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--window-size", type=int, default=32)
    p.add_argument("--last-layers", type=int, default=4)
    p.add_argument("--revisit-threshold", type=float, default=0.95)
    p.add_argument("--trust-remote-code", action="store_true")
    return p.parse_args()


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


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.clip(np.dot(left, right) / denom, -1.0, 1.0)) if denom > 1e-12 else 0.0


def marker_location(ids: list[int], marker_ids: dict[str, list[int]]) -> tuple[str | None, int]:
    for end in range(1, len(ids) + 1):
        for marker, pattern in marker_ids.items():
            if end >= len(pattern) and ids[end - len(pattern):end] == pattern:
                return marker, end - len(pattern)
    return None, len(ids)


def lexical_repetition(ids: list[int], n: int = 4) -> float:
    grams = [tuple(ids[i:i + n]) for i in range(max(0, len(ids) - n + 1))]
    if not grams:
        return 0.0
    counts = Counter(grams)
    return float(sum(count - 1 for count in counts.values()) / len(grams))


def window_metrics(vectors: np.ndarray, size: int, threshold: float) -> dict[str, Any]:
    windows = []
    for start in range(0, len(vectors), size):
        vector = vectors[start:start + size].mean(axis=0)
        norm = np.linalg.norm(vector)
        windows.append(vector / norm if norm > 1e-12 else vector)
    adjacent = [1.0 - cosine(windows[i - 1], windows[i]) for i in range(1, len(windows))]
    tail = windows[-3:]
    pairs = [cosine(tail[i], tail[j]) for i in range(len(tail)) for j in range(i + 1, len(tail))]
    eligible = max(0, len(windows) - 2)
    revisits = sum(
        max(cosine(windows[i], windows[j]) for j in range(i - 1)) >= threshold
        for i in range(2, len(windows))
    )
    return {
        "window_count": len(windows),
        "terminal_stability": float(np.mean(pairs)) if pairs else None,
        "mean_adjacent_window_distance": float(np.mean(adjacent)) if adjacent else None,
        "semantic_revisit_rate": float(revisits / eligible) if eligible else 0.0,
    }


def run_task(task: dict[str, Any], tokenizer: Any, model: Any, args: argparse.Namespace,
             device: torch.device, marker_ids: dict[str, list[int]]) -> dict[str, Any]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task["prompt"]}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    encoded = {key: value.to(device) for key, value in encoded.items()}
    prompt_length = int(encoded["input_ids"].shape[1])
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
        torch.cuda.synchronize(device)
    started = time.perf_counter()
    stopper = StoppingCriteriaList([StopAfterTokenSequence(list(marker_ids.values()))])
    with torch.inference_mode():
        output = model.generate(
            **encoded, max_new_tokens=args.max_new_tokens, do_sample=False,
            stopping_criteria=stopper, pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            return_dict_in_generate=True,
        )
        sequence = output.sequences
        generated_ids = sequence[0, prompt_length:].tolist()
        marker, semantic_end = marker_location(generated_ids, marker_ids)
        if marker == "<READY>":
            termination = "ready"
        elif marker == "<UNRESOLVED>":
            termination = "unresolved"
        elif len(generated_ids) >= args.max_new_tokens:
            termination = "budget_exhausted"
        else:
            termination = "ended_without_marker"
        forward = model(input_ids=sequence, attention_mask=torch.ones_like(sequence),
                        output_hidden_states=True, use_cache=False, return_dict=True)
        layers = forward.hidden_states[-args.last_layers:]
        per_layer = [F.normalize(x[0, prompt_length:prompt_length + semantic_end].float(), p=2, dim=-1) for x in layers]
        token_vectors = F.normalize(torch.stack(per_layer).mean(dim=0), p=2, dim=-1).cpu().numpy()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    metrics = window_metrics(token_vectors, args.window_size, args.revisit_threshold) if len(token_vectors) else {
        "window_count": 0, "terminal_stability": None,
        "mean_adjacent_window_distance": None, "semantic_revisit_rate": 0.0,
    }
    text = tokenizer.decode(generated_ids, skip_special_tokens=True)
    semantic_ids = generated_ids[:semantic_end]
    return {
        "termination_status": termination,
        "convergence_tokens": len(generated_ids),
        **metrics,
        "lexical_repetition_rate": lexical_repetition(semantic_ids),
        "path_reversal_count": sum(len(re.findall(pattern, text, flags=re.I)) for pattern in REVERSAL_PATTERNS),
        "probe_text": text,
        "runtime_ms": (time.perf_counter() - started) * 1000.0,
        "peak_memory_mb": float(torch.cuda.max_memory_allocated(device) / 1024**2) if device.type == "cuda" else 0.0,
    }


def write_report(path: Path, payload: dict[str, Any]) -> None:
    results = payload["results"]
    successful = [x for x in results if x["status"] == "success"]
    counts = Counter(x["termination_status"] for x in successful)
    lines = ["# 单次预推理收敛性报告", "", "本报告不评价答案正确性，也不与 L1–L5 比较。", "", "## 汇总", ""]
    for name in ("ready", "unresolved", "budget_exhausted", "ended_without_marker"):
        lines.append(f"- `{name}`：{counts[name]}")
    if successful:
        lines.append(f"- 平均预推理 Token：{statistics.mean(x['convergence_tokens'] for x in successful):.2f}")
    lines.extend(["", "## 逐题结果", ""])
    for item in results:
        lines.extend([
            f"### {item['task_id']}", "",
            f"- 状态：`{item.get('termination_status', 'error')}`",
            f"- Token：{item.get('convergence_tokens', '')}",
            f"- 末段稳定度：{item.get('terminal_stability')}",
            f"- 语义回访率：{item.get('semantic_revisit_rate')}",
            f"- 词面重复率：{item.get('lexical_repetition_rate')}",
            f"- 路径反转次数：{item.get('path_reversal_count')}", "",
            "```text", item.get("probe_text", item.get("error", "")), "```", "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.max_new_tokens < 1 or args.window_size < 1 or args.last_layers < 1:
        raise ValueError("Token、窗口和层数参数必须为正数")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device(args.device)
    dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[args.dtype]
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=args.trust_remote_code)
    model = AutoModelForCausalLM.from_pretrained(args.model_path, torch_dtype=dtype,
        trust_remote_code=args.trust_remote_code, attn_implementation="sdpa").to(device).eval()
    marker_ids = {m: tokenizer.encode(m, add_special_tokens=False) for m in MARKERS}
    tasks = load_tasks(Path(args.input_file))
    results = []
    for task in tasks:
        base = {key: task[key] for key in ("task_id", "task_type", "difficulty_level")}
        try:
            result = {**base, **run_task(task, tokenizer, model, args, device, marker_ids), "status": "success", "error": ""}
        except Exception as exc:
            result = {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(task["task_id"], result["status"], result.get("termination_status", ""))
    payload = {
        "experiment": {
            "method": "single_pass_bounded_prereasoning_convergence",
            "created_at": datetime.now(timezone.utc).isoformat(), "model_path": args.model_path,
            "input_file": str(Path(args.input_file).resolve()), "device": str(device), "dtype": args.dtype,
            "seed": args.seed, "max_new_tokens": args.max_new_tokens, "window_size": args.window_size,
            "last_layers": args.last_layers, "revisit_threshold": args.revisit_threshold,
            "sampling": False, "full_answer_evaluation": False, "label_comparison": False,
            "python_version": platform.python_version(), "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
        }, "results": results,
    }
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore"); writer.writeheader(); writer.writerows(results)
    write_report(output / "report.md", payload)


if __name__ == "__main__":
    main()
