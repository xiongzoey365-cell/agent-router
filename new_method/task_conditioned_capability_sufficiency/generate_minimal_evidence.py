#!/usr/bin/env python3
"""让被测模型对 25 道题只生成最小结构化行为证据。"""

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

from common import MODEL_SCHEMA, MODEL_SYSTEM_PROMPT, load_tasks, parse_json_object, schema_diagnostics, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--input-file", default="测试数据.txt")
    parser.add_argument("--output-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/model_evidence.json")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def dtype_for(name: str) -> torch.dtype:
    return {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[name]


def generate(task: dict[str, Any], model: Any, tokenizer: Any, device: torch.device, limit: int) -> dict[str, Any]:
    messages = [{"role": "system", "content": MODEL_SYSTEM_PROMPT}, {"role": "user", "content": str(task["prompt"])}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    encoded = {key: value.to(device) for key, value in encoded.items()}
    prompt_tokens = int(encoded["input_ids"].shape[1])
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **encoded, max_new_tokens=limit, do_sample=False, temperature=None, top_p=None, top_k=None,
            pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
        )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    ids = output[0, prompt_tokens:].tolist()
    raw = tokenizer.decode(ids, skip_special_tokens=True)
    parsed = parse_json_object(raw)
    return {
        "task_id": task["task_id"], "task_type": task["task_type"], "prompt": task["prompt"],
        "raw_output": raw, "parsed_output": parsed["parsed"],
        "parser": {key: value for key, value in parsed.items() if key != "parsed"},
        "schema": schema_diagnostics(parsed["parsed"], MODEL_SCHEMA),
        "token_ids": {"prompt": encoded["input_ids"][0].tolist(), "generated": ids},
        "generation": {"prompt_tokens": prompt_tokens, "generated_tokens": len(ids), "elapsed_ms": (time.perf_counter() - started) * 1000.0},
        "status": "success", "error": "",
    }


def main() -> None:
    args = parse_args()
    if args.max_new_tokens < 1:
        raise ValueError("max-new-tokens 必须大于 0")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    tasks = load_tasks(Path(args.input_file))
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA，但当前环境不可用")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=args.trust_remote_code)
    model = AutoModelForCausalLM.from_pretrained(args.model_path, torch_dtype=dtype_for(args.dtype), trust_remote_code=args.trust_remote_code, low_cpu_mem_usage=True).to(device)
    model.eval()
    results = []
    for task in tasks:
        try:
            results.append(generate(task, model, tokenizer, device, args.max_new_tokens))
        except Exception as exc:
            results.append({"task_id": task["task_id"], "task_type": task["task_type"], "prompt": task["prompt"], "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    write_json(Path(args.output_file), {
        "metadata": {
            "method": "task_conditioned_capability_sufficiency", "stage": "model_evidence",
            "model": args.model_name or Path(args.model_path).name, "model_path": args.model_path,
            "input_file": args.input_file, "task_count": len(tasks), "uses_training": False,
            "uses_hidden_states": False, "generates_final_answer": False, "uses_answer_correctness": False, "system_prompt": MODEL_SYSTEM_PROMPT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "generation_config": {"do_sample": False, "enable_thinking": False, "max_new_tokens": args.max_new_tokens, "seed": args.seed, "dtype": args.dtype, "device": str(device)},
            "runtime": {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__, "cuda": torch.version.cuda},
        }, "results": results,
    })


if __name__ == "__main__":
    main()
