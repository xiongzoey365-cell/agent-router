#!/usr/bin/env python3
"""Run independent six-dimension and original-question-only Qwen3-8B arms.

Each arm saves the rendered prompt, raw model output, token IDs, and the raw
full-sequence hidden state for the embedding output and every decoder layer.
The baseline arm contains no system message or auxiliary instruction.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


EXPERIMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXPERIMENT_DIR.parent
DEFAULT_INPUT = REPO_ROOT / "测试数据.txt"
DEFAULT_OUTPUT = EXPERIMENT_DIR / "outputs"
DEFAULT_MODEL = (
    "/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)

SIX_DIMENSION_PROMPT = """你现在只分析应当如何作答，不直接回答或求解用户题目。请针对当前题目，依次从以下六个维度说明解题者应如何处理：

1. 推理与规划能力（Reasoning & Planning）
2. 指令遵循与角色遵从能力（Instruction Following & Role Adherence）
3. 通信与社会推理能力（Communication & Social Reasoning）
4. 自我批评与验证能力（Self-Critique & Verification）
5. 记忆与上下文管理能力（Memory & Context Management）
6. 工具使用与动作落地能力（Tool Use & Action Grounding）

必须按这六个维度输出，但每个维度内部可以自由、自然地表达，不规定固定子项、长度或写法。只说明该维度在当前题目中实际需要关注和采取的做法，不进行能力打分，不为了凑齐内容而添加无关信息；如果某个维度在本题中没有明显体现，直接说明该维度没有明显体现。保留题目给出的条件、角色、格式和边界，不添加没有依据的事实。没有真正执行查询、计算、代码、测试或其他工具时，不得声称已经执行。不要给出题目的最终答案、最终选项、最终代码或完整证明。"""

ARM_CONFIGS = {
    "six_dimension": {
        "description": "统一六维 system prompt；只输出六维解题方式，不继续作答。",
        "system_prompt": SIX_DIMENSION_PROMPT,
    },
    "no_prompt_baseline": {
        "description": "仅原始题目 user 消息；无 system prompt、六维提示或其他辅助提示。",
        "system_prompt": None,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model-path", default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--six-dimension-max-new-tokens", type=int, default=2048)
    parser.add_argument("--baseline-max-new-tokens", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=tuple(ARM_CONFIGS),
        default=list(ARM_CONFIGS),
        help="Experiment arms to run (default: both).",
    )
    parser.add_argument(
        "--task-ids",
        nargs="*",
        default=None,
        help="Optional task IDs for a smoke test or partial run.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--trust-remote-code",
        action=argparse.BooleanOptionalAction,
        default=True,
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


def read_tasks(path: Path, selected_ids: list[str] | None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"{path} 中缺少非空 tasks 数组")
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or "task_id" not in task or "prompt" not in task:
            raise ValueError(f"tasks[{index}] 缺少 task_id 或 prompt")
    if selected_ids is None:
        return tasks
    by_id = {str(task["task_id"]): task for task in tasks}
    missing = [task_id for task_id in selected_ids if task_id not in by_id]
    if missing:
        raise ValueError(f"未知 task_id: {missing}")
    return [by_id[task_id] for task_id in selected_ids]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_messages(arm: str, task_prompt: str) -> list[dict[str, str]]:
    system_prompt = ARM_CONFIGS[arm]["system_prompt"]
    if system_prompt is None:
        return [{"role": "user", "content": task_prompt}]
    return [
        {"role": "system", "content": str(system_prompt)},
        {"role": "user", "content": task_prompt},
    ]


def build_model_input(
    tokenizer: Any,
    arm: str,
    task_prompt: str,
    device: torch.device,
) -> tuple[list[dict[str, str]], str, dict[str, torch.Tensor]]:
    messages = render_messages(arm, task_prompt)
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    return messages, rendered, {key: value.to(device) for key, value in encoded.items()}


def termination_status(tokenizer: Any, generated_ids: list[int], limit: int) -> str:
    eos = tokenizer.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    if generated_ids and generated_ids[-1] in eos_ids:
        return "eos"
    if len(generated_ids) >= limit:
        return "token_budget"
    return "other"


def tensor_from_layer_output(output: Any) -> torch.Tensor:
    value = output[0] if isinstance(output, tuple) else output
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"层输出不是 Tensor: {type(value)!r}")
    return value


def capture_raw_hidden_states(
    path: Path,
    model: Any,
    full_input_ids: torch.Tensor,
    full_attention_mask: torch.Tensor,
    prompt_token_count: int,
    generated_token_count: int,
) -> dict[str, Any]:
    """Capture the same full-sequence states represented by HF hidden_states.

    Hooks copy each state to CPU immediately, avoiding retention of every layer
    on the GPU. Values, BF16/FP16 dtype, batch/sequence axes, and token positions
    are preserved. The saved tuple is: embedding output, outputs after decoder
    layers 0..N-2, and the final normalized output.
    """
    backbone = getattr(model, "model", None)
    layers = getattr(backbone, "layers", None)
    embedding = getattr(backbone, "embed_tokens", None)
    final_norm = getattr(backbone, "norm", None)
    if backbone is None or layers is None or embedding is None or final_norm is None:
        raise RuntimeError("无法定位 Qwen backbone 的 embed_tokens/layers/norm")

    captured: dict[str, torch.Tensor] = {}
    handles = []

    def hook_for(label: str) -> Callable[[Any, Any, Any], None]:
        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            captured[label] = tensor_from_layer_output(output).detach().cpu()

        return hook

    handles.append(embedding.register_forward_hook(hook_for("embedding")))
    for index, layer in enumerate(layers[:-1]):
        handles.append(layer.register_forward_hook(hook_for(f"decoder_{index}")))
    handles.append(final_norm.register_forward_hook(hook_for("final_norm")))

    try:
        with torch.inference_mode():
            backbone(
                input_ids=full_input_ids,
                attention_mask=full_attention_mask,
                use_cache=False,
                output_hidden_states=False,
                return_dict=True,
            )
    finally:
        for handle in handles:
            handle.remove()

    labels = ["embedding"] + [f"decoder_{index}" for index in range(len(layers) - 1)] + ["final_norm"]
    missing = [label for label in labels if label not in captured]
    if missing:
        raise RuntimeError(f"隐藏状态捕获不完整: {missing}")
    raw_states = tuple(captured[label] for label in labels)
    artifact = {
        "format_version": 1,
        "description": (
            "Raw full-sequence hidden states for the rendered prompt and generated "
            "tokens. No pooling, token slicing, normalization, quantization, feature "
            "extraction, or dtype conversion was applied; tensors were only detached "
            "and transferred losslessly to CPU for serialization."
        ),
        "input_ids": full_input_ids.detach().cpu(),
        "attention_mask": full_attention_mask.detach().cpu(),
        "prompt_token_count": prompt_token_count,
        "generated_token_count": generated_token_count,
        "state_labels": labels,
        "hidden_states": raw_states,
    }
    torch.save(artifact, path)
    metadata = {
        "file": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "tensor_count": len(raw_states),
        "state_labels": labels,
        "shapes": [list(tensor.shape) for tensor in raw_states],
        "dtypes": [str(tensor.dtype) for tensor in raw_states],
        "sequence_scope": "rendered prompt plus every generated token",
        "processing": "detach and lossless device transfer to CPU only",
    }
    del artifact, raw_states, captured
    return metadata


def write_aggregate_outputs(records_dir: Path, arm_dir: Path, arm: str) -> None:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(records_dir.glob("*.json"))]
    with (arm_dir / "all_outputs.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    lines = [f"# {arm}", "", ARM_CONFIGS[arm]["description"], ""]
    for index, record in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {record['task_id']}",
                "",
                "### Original task",
                "",
                str(record["task_prompt"]),
                "",
                "### Raw model output",
                "",
                str(record["raw_output"]),
                "",
            ]
        )
    (arm_dir / "all_outputs.md").write_text("\n".join(lines), encoding="utf-8")


def prepare_arm_directories(output_dir: Path, arm: str) -> dict[str, Path]:
    arm_dir = output_dir / arm
    directories = {
        "arm": arm_dir,
        "records": arm_dir / "records",
        "text": arm_dir / "raw_text",
        "hidden": arm_dir / "raw_hidden_states",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    if ARM_CONFIGS[arm]["system_prompt"] is not None:
        (arm_dir / "system_prompt.txt").write_text(
            str(ARM_CONFIGS[arm]["system_prompt"]), encoding="utf-8"
        )
    (arm_dir / "prompt_policy.txt").write_text(
        str(ARM_CONFIGS[arm]["description"]), encoding="utf-8"
    )
    return directories


def max_new_tokens_for_arm(args: argparse.Namespace, arm: str) -> int:
    if arm == "six_dimension":
        return args.six_dimension_max_new_tokens
    return args.baseline_max_new_tokens


def main() -> None:
    args = parse_args()
    if args.six_dimension_max_new_tokens < 1 or args.baseline_max_new_tokens < 1:
        raise ValueError("max-new-tokens 必须大于 0")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA 设备，但 torch.cuda.is_available() 为 False")

    input_path = args.input_file.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = read_tasks(input_path, args.task_ids)
    set_seed(args.seed)

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
        "experiment": "six_dimension_output_vs_no_prompt_baseline",
        "model_path": str(args.model_path),
        "input_file": str(input_path),
        "input_sha256": sha256_file(input_path),
        "output_dir": str(output_dir),
        "task_count": len(tasks),
        "task_ids": [str(task["task_id"]) for task in tasks],
        "arms": {
            arm: {
                **ARM_CONFIGS[arm],
                "max_new_tokens": max_new_tokens_for_arm(args, arm),
                "messages": (
                    "system prompt plus original user task"
                    if ARM_CONFIGS[arm]["system_prompt"] is not None
                    else "original user task only"
                ),
            }
            for arm in args.arms
        },
        "generation": {
            "enable_thinking": False,
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "top_k": None,
            "seed": args.seed,
        },
        "hidden_state_capture": {
            "sequence": "rendered prompt plus all generated tokens",
            "states": "embedding output, all decoder-depth states, final normalized output",
            "processing": "none except detach and lossless transfer to CPU",
            "serialization": "torch.save per task and arm",
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
    write_json(output_dir / "input_snapshot.json", {"tasks": tasks})

    arm_directories = {arm: prepare_arm_directories(output_dir, arm) for arm in args.arms}
    total = len(tasks) * len(args.arms)
    completed = 0

    for arm in args.arms:
        dirs = arm_directories[arm]
        token_limit = max_new_tokens_for_arm(args, arm)
        for task in tasks:
            completed += 1
            task_id = str(task["task_id"])
            record_path = dirs["records"] / f"{task_id}.json"
            text_path = dirs["text"] / f"{task_id}.txt"
            hidden_path = dirs["hidden"] / f"{task_id}.pt"
            if (
                not args.overwrite
                and record_path.exists()
                and text_path.exists()
                and hidden_path.exists()
            ):
                print(f"[{completed}/{total}] skip {arm}/{task_id}", flush=True)
                continue

            print(f"[{completed}/{total}] generate {arm}/{task_id}", flush=True)
            # Reset even though greedy decoding is deterministic, so future sampling
            # changes cannot introduce order-dependent state between experiment arms.
            set_seed(args.seed)
            messages, rendered_prompt, encoded = build_model_input(
                tokenizer, arm, str(task["prompt"]), device
            )
            prompt_token_count = int(encoded["input_ids"].shape[1])
            started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    **encoded,
                    max_new_tokens=token_limit,
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
            elapsed_seconds = time.perf_counter() - started

            full_ids = generated.sequences
            generated_tensor = full_ids[:, prompt_token_count:]
            generated_ids = generated_tensor[0].tolist()
            raw_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
            full_attention_mask = torch.ones_like(full_ids, device=device)

            print(f"[{completed}/{total}] hidden {arm}/{task_id}", flush=True)
            hidden_metadata = capture_raw_hidden_states(
                hidden_path,
                model,
                full_ids,
                full_attention_mask,
                prompt_token_count,
                len(generated_ids),
            )
            text_path.write_text(raw_text, encoding="utf-8")

            record = {
                "arm": arm,
                "task_id": task_id,
                "task_type": task.get("task_type"),
                "difficulty_level": task.get("difficulty_level"),
                "source_benchmark": task.get("source_benchmark"),
                "task_prompt": task["prompt"],
                "messages": messages,
                "rendered_model_prompt": rendered_prompt,
                "prompt_token_ids": encoded["input_ids"][0].detach().cpu().tolist(),
                "generated_token_ids": generated_ids,
                "raw_output": raw_text,
                "generation": {
                    "prompt_tokens": prompt_token_count,
                    "generated_tokens": len(generated_ids),
                    "max_new_tokens": token_limit,
                    "termination": termination_status(tokenizer, generated_ids, token_limit),
                    "elapsed_seconds": elapsed_seconds,
                },
                "artifacts": {
                    "raw_text": str(text_path.relative_to(output_dir)),
                    "raw_hidden_states": str(hidden_path.relative_to(output_dir)),
                    "hidden_state_metadata": hidden_metadata,
                },
            }
            write_json(record_path, record)
            write_aggregate_outputs(dirs["records"], dirs["arm"], arm)

            del generated, generated_tensor, full_ids, full_attention_mask, encoded
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()

    for arm in args.arms:
        dirs = arm_directories[arm]
        write_aggregate_outputs(dirs["records"], dirs["arm"], arm)

    completion = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "arms": {},
    }
    for arm in args.arms:
        dirs = arm_directories[arm]
        completion["arms"][arm] = {
            "records": len(list(dirs["records"].glob("*.json"))),
            "raw_texts": len(list(dirs["text"].glob("*.txt"))),
            "raw_hidden_state_files": len(list(dirs["hidden"].glob("*.pt"))),
        }
    write_json(output_dir / "completion.json", completion)
    print(f"complete: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
