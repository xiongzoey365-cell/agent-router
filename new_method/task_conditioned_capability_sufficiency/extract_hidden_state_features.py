#!/usr/bin/env python3
"""独立隐藏状态轨：观察最小结构化证据生成过程中的潜在状态变化。"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import DIMENSIONS, read_json, write_json


METRIC_NAMES = (
    "dispersion_entropy",
    "mean_step_drift",
    "direction_change",
    "terminal_instability",
    "cross_layer_disagreement",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument(
        "--input-file",
        default="outputs/task_conditioned_capability_sufficiency_no_answer/model_evidence.json",
    )
    parser.add_argument(
        "--output-file",
        default=(
            "outputs/task_conditioned_capability_sufficiency_no_answer/"
            "hidden_state/latent_metrics.json"
        ),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--last-layers", type=int, default=4)
    parser.add_argument("--minimum-field-tokens", type=int, default=3)
    parser.add_argument("--terminal-tokens", type=int, default=8)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def dtype_for(name: str) -> torch.dtype:
    return {
        "bf16": torch.bfloat16,
        "fp16": torch.float16,
        "fp32": torch.float32,
    }[name]


def rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    similarity = float(np.dot(left, right) / denominator)
    return float(np.clip((1.0 - np.clip(similarity, -1.0, 1.0)) / 2.0, 0.0, 1.0))


def effective_rank_entropy(trajectory: np.ndarray) -> float:
    if len(trajectory) < 2:
        return 0.0
    centered = trajectory - trajectory.mean(axis=0, keepdims=True)
    gram = centered @ centered.T
    eigenvalues = np.linalg.eigvalsh(gram.astype(np.float64))
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    eigenvalues = eigenvalues[eigenvalues > 1e-12]
    if len(eigenvalues) <= 1:
        return 0.0
    probabilities = eigenvalues / eigenvalues.sum()
    entropy = -float(np.sum(probabilities * np.log(probabilities)))
    return float(np.clip(entropy / math.log(len(probabilities)), 0.0, 1.0))


def pairwise_instability(trajectory: np.ndarray) -> float:
    distances = [
        cosine_distance(trajectory[left], trajectory[right])
        for left in range(len(trajectory))
        for right in range(left + 1, len(trajectory))
    ]
    return float(np.mean(distances)) if distances else 0.0


def cross_layer_disagreement(layer_states: np.ndarray) -> float:
    # [layers, tokens, hidden]
    values: list[float] = []
    for token_index in range(layer_states.shape[1]):
        for left in range(layer_states.shape[0]):
            for right in range(left + 1, layer_states.shape[0]):
                values.append(
                    cosine_distance(
                        layer_states[left, token_index],
                        layer_states[right, token_index],
                    )
                )
    return float(np.mean(values)) if values else 0.0


def trajectory_metrics(
    layer_states: np.ndarray,
    terminal_tokens: int,
) -> tuple[dict[str, float], np.ndarray]:
    norms = np.linalg.norm(layer_states, axis=-1, keepdims=True)
    normalized_layers = layer_states / np.clip(norms, 1e-12, None)
    trajectory = normalized_layers.mean(axis=0)
    trajectory /= np.clip(np.linalg.norm(trajectory, axis=-1, keepdims=True), 1e-12, None)

    steps = [
        cosine_distance(trajectory[index - 1], trajectory[index])
        for index in range(1, len(trajectory))
    ]
    deltas = np.diff(trajectory, axis=0)
    turns = [
        cosine_distance(deltas[index - 1], deltas[index])
        for index in range(1, len(deltas))
    ]
    terminal = trajectory[-min(terminal_tokens, len(trajectory)):]
    metrics = {
        "dispersion_entropy": effective_rank_entropy(trajectory),
        "mean_step_drift": float(np.mean(steps)) if steps else 0.0,
        "direction_change": float(np.mean(turns)) if turns else 0.0,
        "terminal_instability": pairwise_instability(terminal),
        "cross_layer_disagreement": cross_layer_disagreement(normalized_layers),
    }
    return metrics, trajectory


def substantive(value: Any) -> bool:
    """判断字段是否含实际证据；false/null 和全空容器不激活隐藏维度。"""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        return any(substantive(item) for item in value)
    if isinstance(value, dict):
        return any(substantive(item) for item in value.values())
    return False


def top_level_value_spans(raw: str) -> dict[str, tuple[int, int]]:
    decoder = json.JSONDecoder()
    spans: dict[str, tuple[int, int]] = {}
    cursor = 0
    for field in DIMENSIONS:
        match = re.search(rf'"{re.escape(field)}"\s*:\s*', raw[cursor:])
        if match is None:
            continue
        start = cursor + match.end()
        try:
            _, end = decoder.raw_decode(raw, start)
        except json.JSONDecodeError:
            continue
        spans[field] = (start, end)
        cursor = end
    return spans


def token_indices_for_span(
    offsets: list[tuple[int, int]],
    span: tuple[int, int],
) -> list[int]:
    start, end = span
    return [
        index
        for index, (token_start, token_end) in enumerate(offsets)
        if token_end > start and token_start < end
    ]


def collect_selected_layers(
    model: Any,
    token_ids: list[int],
    device: torch.device,
    last_layers: int,
) -> tuple[list[int], list[np.ndarray]]:
    backbone = getattr(model, "model", None)
    layers = getattr(backbone, "layers", None)
    if backbone is None or layers is None:
        raise RuntimeError("无法定位 model.model.layers，当前模型结构不受支持")
    if last_layers < 1 or last_layers > len(layers):
        raise ValueError(f"last-layers 必须位于 [1, {len(layers)}]")

    selected_indices = list(range(len(layers) - last_layers, len(layers)))
    captured: dict[int, np.ndarray] = {}
    handles = []

    def hook_for(layer_index: int):
        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            hidden = output[0] if isinstance(output, tuple) else output
            captured[layer_index] = hidden[0].detach().float().cpu().numpy()
        return hook

    for layer_index in selected_indices:
        handles.append(layers[layer_index].register_forward_hook(hook_for(layer_index)))

    ids = torch.tensor([token_ids], dtype=torch.long, device=device)
    try:
        with torch.inference_mode():
            backbone(
                input_ids=ids,
                attention_mask=torch.ones_like(ids),
                use_cache=False,
                return_dict=True,
            )
    finally:
        for handle in handles:
            handle.remove()

    if set(captured) != set(selected_indices):
        raise RuntimeError("未捕获全部指定层的 Hidden States")
    return selected_indices, [captured[index] for index in selected_indices]


def analyze_item(
    item: dict[str, Any],
    model: Any,
    tokenizer: Any,
    device: torch.device,
    last_layers: int,
    minimum_tokens: int,
    terminal_tokens: int,
) -> dict[str, Any]:
    base = {
        "task_id": item.get("task_id"),
        "task_type": item.get("task_type"),
    }
    if item.get("status") != "success":
        return {**base, "status": "error", "error": "model evidence generation failed"}

    token_payload = item.get("token_ids")
    if not isinstance(token_payload, dict):
        return {**base, "status": "error", "error": "source has no exact token_ids"}
    prompt_ids = token_payload.get("prompt")
    generated_ids = token_payload.get("generated")
    if not isinstance(prompt_ids, list) or not isinstance(generated_ids, list):
        return {**base, "status": "error", "error": "invalid token_ids"}

    raw = str(item.get("raw_output", ""))
    retokenized = tokenizer(
        raw,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    content_ids = [int(value) for value in retokenized["input_ids"]]
    offsets = [(int(left), int(right)) for left, right in retokenized["offset_mapping"]]
    if generated_ids[:len(content_ids)] != content_ids:
        return {
            **base,
            "status": "error",
            "error": "decoded output does not round-trip to generated token IDs",
        }

    full_ids = [int(value) for value in prompt_ids + generated_ids]
    layer_indices, layer_outputs = collect_selected_layers(
        model, full_ids, device, last_layers
    )
    parsed = item.get("parsed_output") if isinstance(item.get("parsed_output"), dict) else {}
    spans = top_level_value_spans(raw)
    fields: dict[str, Any] = {}
    available_scores: list[float] = []
    previous_terminal: np.ndarray | None = None

    for field in DIMENSIONS:
        evidence_present = substantive(parsed.get(field))
        if field not in spans:
            fields[field] = {
                "measurement_status": "missing_field_span",
                "evidence_present": evidence_present,
                "token_count": 0,
                "metrics": None,
                "latent_load_proxy": None,
            }
            continue

        field_token_indices = token_indices_for_span(offsets, spans[field])
        prediction_positions = [
            len(prompt_ids) + token_index - 1 for token_index in field_token_indices
        ]
        prediction_positions = [position for position in prediction_positions if position >= 0]
        if not evidence_present:
            fields[field] = {
                "measurement_status": "empty_evidence",
                "evidence_present": False,
                "token_count": len(prediction_positions),
                "metrics": None,
                "latent_load_proxy": None,
            }
            continue
        if len(prediction_positions) < minimum_tokens:
            fields[field] = {
                "measurement_status": "too_short",
                "evidence_present": True,
                "token_count": len(prediction_positions),
                "metrics": None,
                "latent_load_proxy": None,
            }
            continue

        layer_states = np.stack(
            [layer[prediction_positions] for layer in layer_outputs], axis=0
        )
        metrics, trajectory = trajectory_metrics(layer_states, terminal_tokens)
        boundary_jump = (
            cosine_distance(previous_terminal, trajectory[0])
            if previous_terminal is not None else None
        )
        previous_terminal = trajectory[-1]
        score = float(np.mean([metrics[name] for name in METRIC_NAMES]))
        available_scores.append(score)
        fields[field] = {
            "measurement_status": "available",
            "evidence_present": True,
            "token_count": len(prediction_positions),
            "metrics": {name: rounded(value) for name, value in metrics.items()},
            "boundary_jump_from_previous_available_field": rounded(boundary_jump),
            "latent_load_proxy": rounded(score),
        }

    return {
        **base,
        "observation_source": "hidden_states",
        "dimension_latent_load": fields,
        "available_dimensions": [
            field for field in DIMENSIONS
            if fields[field]["measurement_status"] == "available"
        ],
        "overall_latent_load_proxy": rounded(
            float(np.mean(available_scores)) if available_scores else None
        ),
        "diagnostics": {
            "strict_json_valid": bool(item.get("parser", {}).get("strict_json_valid")),
            "prompt_tokens": len(prompt_ids),
            "generated_tokens": len(generated_ids),
            "retokenized_content_tokens": len(content_ids),
            "selected_layer_indices_zero_based": layer_indices,
        },
        "status": "success",
        "error": "",
    }


def main() -> None:
    args = parse_args()
    if args.minimum_field_tokens < 3:
        raise ValueError("minimum-field-tokens 至少为 3")
    if args.terminal_tokens < 2:
        raise ValueError("terminal-tokens 至少为 2")
    source = read_json(Path(args.input_file))
    items = source.get("results") if isinstance(source, dict) else None
    if not isinstance(items, list):
        raise ValueError("输入文件必须包含 results 数组")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定了 CUDA，但当前环境不可用")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=args.trust_remote_code,
        use_fast=True,
    )
    if not tokenizer.is_fast:
        raise RuntimeError("字段位置对齐需要 fast tokenizer")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=dtype_for(args.dtype),
        trust_remote_code=args.trust_remote_code,
        low_cpu_mem_usage=True,
    ).to(device)
    model.eval()

    results = []
    for item in items:
        try:
            results.append(analyze_item(
                item,
                model,
                tokenizer,
                device,
                args.last_layers,
                args.minimum_field_tokens,
                args.terminal_tokens,
            ))
        except Exception as exc:
            results.append({
                "task_id": item.get("task_id"),
                "task_type": item.get("task_type"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    write_json(Path(args.output_file), {
        "metadata": {
            "method": "structured_minimal_evidence_hidden_state",
            "stage": "independent_hidden_state_track",
            "source": args.input_file,
            "model_path": args.model_path,
            "uses_llm_judge_outputs": False,
            "fused_with_llm_judge": False,
            "uses_training": False,
            "uses_answer_correctness": False,
            "generates_final_answer": False,
            "hidden_state_semantics": (
                "Exploratory latent-load proxy during minimal-evidence generation; "
                "not calibrated capability sufficiency or objective difficulty."
            ),
            "feature_formula": "equal mean of five bounded raw hidden-state metrics",
            "last_layers": args.last_layers,
            "minimum_field_tokens": args.minimum_field_tokens,
            "terminal_tokens": args.terminal_tokens,
            "dtype": args.dtype,
            "device": str(device),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "runtime": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "cuda": torch.version.cuda,
            },
        },
        "results": results,
    })


if __name__ == "__main__":
    main()
