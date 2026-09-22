#!/usr/bin/env python3
"""Generate one pre-execution paragraph per task and save raw hidden states."""

from __future__ import annotations

import argparse
import gc
import json
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


EXPERIMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXPERIMENT_DIR.parent
DEFAULT_INPUT = REPO_ROOT / "测试数据.txt"
DEFAULT_OUTPUT_DIR = EXPERIMENT_DIR / "outputs"
DEFAULT_MODEL = (
    "/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)

SYSTEM_PROMPT = """不要直接回答或求解当前题目。请把它转化为一段供后续执行使用的工作便笺：即使读者不再查看原题，也应能据此继续处理任务。便笺应自然地保留所有可能影响结果的对象、条件、关系、例外、指令和表达边界，并形成一条可执行的处理路线；对尚不能确定之处，说明需要区分的可能情况、判断依据和检验办法；如果某种查询、计算、检索、代码执行或其他外部手段有助于推进任务，说明适合采用什么手段、向其提供什么关键信息、希望获得什么证据，以及不同结果将如何影响后续处理。不得添加题目未提供的事实，不得把计划中的操作写成已经完成，不得评价自己的能力，不得使用标题、列表或固定栏目，也不要给出题目的最终答案。只输出一个自然连贯、自足且尽可能精炼的段落。题目没有提供依据的方面不必强行涉及，内容取舍本身也是回答的一部分。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model-path", default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--trust-remote-code", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-task files. By default completed tasks are skipped.",
    )
    return parser.parse_args()


def resolve_dtype(name: str) -> torch.dtype:
    return {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[name]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def read_tasks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"{path} 中缺少非空 tasks 数组")
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or "task_id" not in task or "prompt" not in task:
            raise ValueError(f"tasks[{index}] 缺少 task_id 或 prompt")
    return tasks


def build_model_input(tokenizer: Any, task_prompt: str, device: torch.device) -> tuple[str, dict[str, torch.Tensor]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_prompt},
    ]
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    return rendered, {key: value.to(device) for key, value in encoded.items()}


def termination_status(tokenizer: Any, generated_ids: list[int], limit: int) -> str:
    eos = tokenizer.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    if generated_ids and generated_ids[-1] in eos_ids:
        return "eos"
    if len(generated_ids) >= limit:
        return "token_budget"
    return "other"


def save_raw_hidden_states(
    path: Path,
    model: Any,
    full_input_ids: torch.Tensor,
    full_attention_mask: torch.Tensor,
    prompt_token_count: int,
    generated_token_count: int,
) -> dict[str, Any]:
    """Save every returned hidden-state tensor without pooling or numeric conversion."""
    with torch.inference_mode():
        forward_output = model(
            input_ids=full_input_ids,
            attention_mask=full_attention_mask,
            use_cache=False,
            output_hidden_states=True,
            return_dict=True,
        )

    if forward_output.hidden_states is None:
        raise RuntimeError("模型没有返回 hidden_states")

    # Moving to CPU is required for durable serialization. Tensor values, dtype,
    # rank, batch dimension, sequence positions and hidden dimensions are retained.
    raw_states = tuple(state.detach().cpu() for state in forward_output.hidden_states)
    artifact = {
        "format_version": 1,
        "description": (
            "Raw full-sequence hidden states returned by Transformers with "
            "output_hidden_states=True; no pooling, slicing, normalization, "
            "quantization, feature extraction, or dtype conversion was applied."
        ),
        "input_ids": full_input_ids.detach().cpu(),
        "attention_mask": full_attention_mask.detach().cpu(),
        "prompt_token_count": prompt_token_count,
        "generated_token_count": generated_token_count,
        "hidden_states": raw_states,
    }
    torch.save(artifact, path)
    metadata = {
        "file": path.name,
        "tensor_count": len(raw_states),
        "shapes": [list(tensor.shape) for tensor in raw_states],
        "dtypes": [str(tensor.dtype) for tensor in raw_states],
        "includes_embedding_output": True,
        "processing": "detach and device transfer to CPU only",
    }
    del forward_output, raw_states, artifact
    return metadata


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl_from_records(records_dir: Path, output_path: Path) -> None:
    records = []
    for path in sorted(records_dir.glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    if args.max_new_tokens < 1:
        raise ValueError("--max-new-tokens 必须大于 0")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA 设备，但 torch.cuda.is_available() 为 False")

    set_seed(args.seed)
    tasks = read_tasks(args.input_file)
    output_dir = args.output_dir.resolve()
    records_dir = output_dir / "records"
    texts_dir = output_dir / "raw_text"
    hidden_dir = output_dir / "raw_hidden_states"
    for directory in (output_dir, records_dir, texts_dir, hidden_dir):
        directory.mkdir(parents=True, exist_ok=True)

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

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "single_paragraph_pre_execution_note",
        "model_path": str(args.model_path),
        "input_file": str(args.input_file.resolve()),
        "output_dir": str(output_dir),
        "task_count": len(tasks),
        "system_prompt": SYSTEM_PROMPT,
        "generation": {
            "enable_thinking": False,
            "do_sample": False,
            "max_new_tokens": args.max_new_tokens,
            "seed": args.seed,
        },
        "hidden_state_capture": {
            "source": "one full forward pass over rendered prompt plus generated token IDs",
            "output_hidden_states": True,
            "use_cache": False,
            "saved": "embedding output and every transformer-layer output",
            "processing": "none except detach and lossless transfer to CPU for torch.save",
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "device": str(device),
            "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
            "model_dtype": str(next(model.parameters()).dtype),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "system_prompt.txt").write_text(SYSTEM_PROMPT, encoding="utf-8")

    for index, task in enumerate(tasks, start=1):
        task_id = str(task["task_id"])
        record_path = records_dir / f"{task_id}.json"
        text_path = texts_dir / f"{task_id}.txt"
        hidden_path = hidden_dir / f"{task_id}.pt"
        if not args.overwrite and record_path.exists() and text_path.exists() and hidden_path.exists():
            print(f"[{index}/{len(tasks)}] skip {task_id}: outputs already exist", flush=True)
            continue

        print(f"[{index}/{len(tasks)}] generate {task_id}", flush=True)
        rendered_prompt, encoded = build_model_input(tokenizer, str(task["prompt"]), device)
        prompt_token_count = int(encoded["input_ids"].shape[1])
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                pad_token_id=(tokenizer.pad_token_id or tokenizer.eos_token_id),
                return_dict_in_generate=True,
            )
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed_seconds = time.perf_counter() - started
        generated_tensor = generated.sequences[:, prompt_token_count:]
        generated_ids = generated_tensor[0].tolist()
        raw_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        full_ids = generated.sequences
        full_mask = torch.ones_like(full_ids, device=device)

        print(f"[{index}/{len(tasks)}] hidden states {task_id}", flush=True)
        hidden_metadata = save_raw_hidden_states(
            hidden_path,
            model,
            full_ids,
            full_mask,
            prompt_token_count,
            len(generated_ids),
        )
        text_path.write_text(raw_text, encoding="utf-8")
        record = {
            "task_id": task_id,
            "task_type": task.get("task_type"),
            "difficulty_level": task.get("difficulty_level"),
            "source_benchmark": task.get("source_benchmark"),
            "task_prompt": task["prompt"],
            "rendered_model_prompt": rendered_prompt,
            "prompt_token_ids": encoded["input_ids"][0].detach().cpu().tolist(),
            "generated_token_ids": generated_ids,
            "raw_output": raw_text,
            "generation": {
                "prompt_tokens": prompt_token_count,
                "generated_tokens": len(generated_ids),
                "termination": termination_status(tokenizer, generated_ids, args.max_new_tokens),
                "elapsed_seconds": elapsed_seconds,
            },
            "artifacts": {
                "raw_text": str(text_path.relative_to(output_dir)),
                "raw_hidden_states": str(hidden_path.relative_to(output_dir)),
                "hidden_state_metadata": hidden_metadata,
            },
        }
        write_json(record_path, record)
        write_jsonl_from_records(records_dir, output_dir / "all_outputs.jsonl")
        del generated, generated_tensor, full_ids, full_mask, encoded
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()

    write_jsonl_from_records(records_dir, output_dir / "all_outputs.jsonl")
    print(f"complete: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
