#!/usr/bin/env python3
"""用独立 Judge 提取语义证据；Judge 不直接输出任何分数。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import JUDGE_SCHEMA, JUDGE_SYSTEM_PROMPT, parse_json_object, read_json, schema_diagnostics, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-model-path", required=True)
    parser.add_argument("--judge-model-name", default=None)
    parser.add_argument("--input-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/model_evidence.json")
    parser.add_argument("--output-file", default="outputs/task_conditioned_capability_sufficiency_no_answer/llm_judge/judge_evidence.json")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def dtype_for(name: str) -> torch.dtype:
    return {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[name]


def judge_one(item: dict[str, Any], model: Any, tokenizer: Any, device: torch.device, limit: int) -> dict[str, Any]:
    request = {
        "task": item.get("prompt", ""),
        "model_observable_output": item.get("parsed_output", {}),
        "required_output_schema": JUDGE_SCHEMA,
    }
    messages = [{"role": "system", "content": JUDGE_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    encoded = {key: value.to(device) for key, value in encoded.items()}
    prompt_tokens = int(encoded["input_ids"].shape[1])
    with torch.inference_mode():
        output = model.generate(**encoded, max_new_tokens=limit, do_sample=False, temperature=None, top_p=None, top_k=None, pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id)
    raw = tokenizer.decode(output[0, prompt_tokens:].tolist(), skip_special_tokens=True)
    parsed = parse_json_object(raw)
    forbidden_score_fields = sorted(key for key in parsed["parsed"] if "score" in key.casefold() or "sufficiency" in key.casefold() or "difficulty" in key.casefold())
    return {
        "task_id": item.get("task_id"), "task_type": item.get("task_type"), "raw_judge_output": raw,
        "evidence": parsed["parsed"], "parser": {key: value for key, value in parsed.items() if key != "parsed"},
        "schema": schema_diagnostics(parsed["parsed"], JUDGE_SCHEMA), "forbidden_top_level_score_fields": forbidden_score_fields,
        "status": "success", "error": "",
    }


def main() -> None:
    args = parse_args()
    source = read_json(Path(args.input_file))
    items = source.get("results") if isinstance(source, dict) else None
    if not isinstance(items, list):
        raise ValueError("输入文件必须包含 results 数组")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA，但当前环境不可用")
    tokenizer = AutoTokenizer.from_pretrained(args.judge_model_path, trust_remote_code=args.trust_remote_code)
    model = AutoModelForCausalLM.from_pretrained(args.judge_model_path, torch_dtype=dtype_for(args.dtype), trust_remote_code=args.trust_remote_code, low_cpu_mem_usage=True).to(device)
    model.eval()
    results = []
    for item in items:
        if item.get("status") != "success":
            results.append({"task_id": item.get("task_id"), "task_type": item.get("task_type"), "status": "error", "error": "model evidence generation failed"})
            continue
        try:
            results.append(judge_one(item, model, tokenizer, device, args.max_new_tokens))
        except Exception as exc:
            results.append({"task_id": item.get("task_id"), "task_type": item.get("task_type"), "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    write_json(Path(args.output_file), {
        "metadata": {"method": "task_conditioned_capability_sufficiency", "stage": "judge_evidence", "judge_model": args.judge_model_name or Path(args.judge_model_path).name, "judge_model_path": args.judge_model_path, "source": args.input_file, "judge_assigns_scores": False, "uses_answer_correctness": False, "system_prompt": JUDGE_SYSTEM_PROMPT, "created_at": datetime.now(timezone.utc).isoformat()},
        "results": results,
    })


if __name__ == "__main__":
    main()
