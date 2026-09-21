#!/usr/bin/env python3
"""第一阶段：让 Qwen3-8B 仅生成一次结构化预推理，不生成最终答案。"""

from __future__ import annotations

import argparse
import platform
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

from generic_common import OUTPUT_FIELDS, SYSTEM_PROMPT, extract_json, load_tasks, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument(
        "--output-file",
        default="outputs/phase1_no_training_output_evidence/prereason_outputs.json",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_dtype(name: str) -> torch.dtype:
    return {
        "bf16": torch.bfloat16,
        "fp16": torch.float16,
        "fp32": torch.float32,
    }[name]


def eos_ids(tokenizer: Any) -> set[int]:
    values = tokenizer.eos_token_id
    if values is None:
        return set()
    if isinstance(values, int):
        return {values}
    return {int(value) for value in values}


def build_input(tokenizer: Any, prompt: str, device: torch.device) -> dict[str, torch.Tensor]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    return {name: value.to(device) for name, value in encoded.items()}


def generate_one(
    task: dict[str, Any],
    model: Any,
    tokenizer: Any,
    device: torch.device,
    max_new_tokens: int,
) -> dict[str, Any]:
    encoded = build_input(tokenizer, str(task["prompt"]), device)
    prompt_tokens = int(encoded["input_ids"].shape[1])
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            top_k=None,
            pad_token_id=(
                tokenizer.pad_token_id
                if tokenizer.pad_token_id is not None
                else tokenizer.eos_token_id
            ),
            return_dict_in_generate=True,
        )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    generated_ids = output.sequences[0, prompt_tokens:].tolist()
    raw_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
    parsed = extract_json(raw_text)
    final_id = generated_ids[-1] if generated_ids else None
    stopped_by_eos = final_id in eos_ids(tokenizer)
    termination = "eos" if stopped_by_eos else (
        "token_budget" if len(generated_ids) >= max_new_tokens else "other"
    )

    parsed_payload = parsed["parsed"]
    present_fields = [field for field in OUTPUT_FIELDS if field in parsed_payload]
    return {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "difficulty_level": task["difficulty_level"],
        "prompt": task["prompt"],
        "raw_output": raw_text,
        "parsed_output": parsed_payload,
        "parser": {
            "strict_json_valid": parsed["strict_json_valid"],
            "recovered_json": parsed["recovered_json"],
            "parse_error": parsed["parse_error"],
            "leading_or_trailing_text": parsed["leading_or_trailing_text"],
            "present_fields": present_fields,
        },
        "generation": {
            "prompt_tokens": prompt_tokens,
            "generated_tokens": len(generated_ids),
            "termination_status": termination,
            "elapsed_ms": elapsed_ms,
        },
        "status": "success",
        "error": "",
    }


def main() -> None:
    args = parse_args()
    if args.max_new_tokens < 1:
        raise ValueError("max-new-tokens 必须大于 0")
    set_deterministic_seed(args.seed)
    tasks = load_tasks(Path(args.input_file))
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA，但当前环境不可用")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=args.trust_remote_code,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=resolve_dtype(args.dtype),
        trust_remote_code=args.trust_remote_code,
        low_cpu_mem_usage=True,
    ).to(device)
    model.eval()

    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            results.append(generate_one(task, model, tokenizer, device, args.max_new_tokens))
        except Exception as exc:  # 保留单题错误并继续，避免丢失已完成样本。
            results.append({
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "difficulty_level": task["difficulty_level"],
                "prompt": task["prompt"],
                "raw_output": "",
                "parsed_output": {},
                "parser": {},
                "generation": {},
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    metadata = {
        "method": "phase1_no_training_output_evidence",
        "stage": "phase_1",
        "uses_training": False,
        "uses_task_specific_rules": False,
        "uses_hidden_states": False,
        "uses_self_reported_scores": False,
        "produces_capability_score": False,
        "single_trajectory_per_task": True,
        "system_prompt": SYSTEM_PROMPT,
        "model_path": args.model_path,
        "input_file": args.input_file,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generation_config": {
            "enable_thinking": False,
            "do_sample": False,
            "max_new_tokens": args.max_new_tokens,
            "seed": args.seed,
            "dtype": args.dtype,
            "device": str(device),
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        },
    }
    write_json(Path(args.output_file), {"metadata": metadata, "results": results})


if __name__ == "__main__":
    main()
