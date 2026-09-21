#!/usr/bin/env python3
"""在最小证据内容 token 上分析 Hidden-State 向量序列的窗口级收敛。"""

from __future__ import annotations

import argparse
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import DIMENSIONS, read_json, write_json


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
            "hidden_state_convergence/convergence_metrics.json"
        ),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("bf16", "fp16", "fp32"), default="bf16")
    parser.add_argument("--last-layers", type=int, default=4)
    parser.add_argument("--window-size", type=int, default=8)
    parser.add_argument("--minimum-windows", type=int, default=3)
    parser.add_argument("--maximum-windows", type=int, default=6)
    parser.add_argument("--convergence-threshold", type=float, default=0.02)
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


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / max(norm, 1e-12)


def cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    similarity = float(np.dot(normalize(left), normalize(right)))
    return float(np.clip((1.0 - np.clip(similarity, -1.0, 1.0)) / 2.0, 0.0, 1.0))


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


def substantive_leaves(value: Any) -> list[Any]:
    """按 JSON 文档顺序收集真实证据标量，排除键名、结构符号、null/false。"""
    if value is None or value is False:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (int, float, bool)):
        return [value]
    if isinstance(value, list):
        return [leaf for item in value for leaf in substantive_leaves(item)]
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in substantive_leaves(item)]
    return []


def locate_leaf_spans(
    raw: str,
    field_span: tuple[int, int],
    field_value: Any,
) -> tuple[list[tuple[int, int]], int]:
    """定位叶子证据内容；字符串排除外层引号，失败数单独记录。"""
    field_start, field_end = field_span
    cursor = field_start
    spans: list[tuple[int, int]] = []
    failures = 0
    for leaf in substantive_leaves(field_value):
        literal = json.dumps(leaf, ensure_ascii=False)
        start = raw.find(literal, cursor, field_end)
        if start < 0:
            failures += 1
            continue
        end = start + len(literal)
        if isinstance(leaf, str) and len(literal) >= 2:
            spans.append((start + 1, end - 1))
        else:
            spans.append((start, end))
        cursor = end
    return spans, failures


def token_indices_for_spans(
    offsets: list[tuple[int, int]],
    spans: list[tuple[int, int]],
) -> list[int]:
    indices: list[int] = []
    for index, (token_start, token_end) in enumerate(offsets):
        if any(token_end > start and token_start < end for start, end in spans):
            indices.append(index)
    return indices


def select_fixed_windows(
    token_indices: list[int],
    window_size: int,
    minimum_windows: int,
    maximum_windows: int,
) -> list[list[int]]:
    """构造等长窗口；窗口过多时等距选取固定数量，避免长序列占优。"""
    complete_count = len(token_indices) // window_size
    if complete_count < minimum_windows:
        return []
    candidates = [
        token_indices[index * window_size:(index + 1) * window_size]
        for index in range(complete_count)
    ]
    if len(candidates) <= maximum_windows:
        return candidates
    selected = np.linspace(0, len(candidates) - 1, maximum_windows)
    selected_indices = [int(round(value)) for value in selected]
    # linspace + round 在此参数范围内应唯一；去重是防御性处理。
    unique = list(dict.fromkeys(selected_indices))
    return [candidates[index] for index in unique]


def pairwise_terminal_stability(centroids: np.ndarray) -> float:
    terminal = centroids[-min(3, len(centroids)):]
    distances = [
        cosine_distance(terminal[left], terminal[right])
        for left in range(len(terminal))
        for right in range(left + 1, len(terminal))
    ]
    instability = float(np.mean(distances)) if distances else 0.0
    return float(np.clip(1.0 - instability, 0.0, 1.0))


def convergence_metrics(
    centroids: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    adjacent = [
        cosine_distance(centroids[index - 1], centroids[index])
        for index in range(1, len(centroids))
    ]
    terminal = centroids[-1]
    to_terminal = [cosine_distance(vector, terminal) for vector in centroids]

    split = max(1, len(adjacent) // 2)
    early = float(np.mean(adjacent[:split]))
    late_values = adjacent[split:] or adjacent[-1:]
    late = float(np.mean(late_values))
    decay = (early - late) / (early + late + 1e-12)

    x_values = np.linspace(0.0, 1.0, len(adjacent))
    slope = float(np.polyfit(x_values, np.asarray(adjacent), 1)[0])

    convergence_index: int | None = None
    # 至少保留两个后续转移；最后一个窗口等于终态，不能单独算作收敛。
    for index in range(max(0, len(centroids) - 2)):
        remaining_terminal = to_terminal[index:]
        remaining_adjacent = adjacent[index:] if index < len(adjacent) else []
        if (
            max(remaining_terminal, default=0.0) <= threshold
            and max(remaining_adjacent, default=0.0) <= threshold
        ):
            convergence_index = index
            break

    convergence_fraction = (
        convergence_index / (len(centroids) - 1)
        if convergence_index is not None and len(centroids) > 1
        else None
    )
    return {
        "adjacent_window_distances": [rounded(value) for value in adjacent],
        "adjacent_window_distance_mean": rounded(float(np.mean(adjacent))),
        "distance_to_terminal": [rounded(value) for value in to_terminal],
        "distance_to_terminal_mean": rounded(float(np.mean(to_terminal[:-1]))),
        "early_adjacent_distance": rounded(early),
        "late_adjacent_distance": rounded(late),
        "early_late_decay": rounded(decay),
        "convergence_slope": rounded(slope),
        "terminal_stability": rounded(pairwise_terminal_stability(centroids)),
        "convergence_window_index": convergence_index,
        "convergence_point_fraction": rounded(convergence_fraction),
        "converged": convergence_index is not None,
    }


def aggregate_layer_metrics(per_layer: list[dict[str, Any]]) -> dict[str, Any]:
    scalar_names = (
        "adjacent_window_distance_mean",
        "distance_to_terminal_mean",
        "early_adjacent_distance",
        "late_adjacent_distance",
        "early_late_decay",
        "convergence_slope",
        "terminal_stability",
    )
    aggregated = {
        name: rounded(float(np.mean([layer[name] for layer in per_layer])))
        for name in scalar_names
    }
    points = [
        layer["convergence_point_fraction"]
        if layer["convergence_point_fraction"] is not None else 1.0
        for layer in per_layer
    ]
    aggregated.update({
        "convergence_point_fraction_or_one": rounded(float(np.mean(points))),
        "converged_layer_rate": rounded(
            sum(bool(layer["converged"]) for layer in per_layer) / len(per_layer)
        ),
    })
    return aggregated


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
    selected = list(range(len(layers) - last_layers, len(layers)))
    captured: dict[int, np.ndarray] = {}
    handles = []

    def hook_for(layer_index: int):
        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            hidden = output[0] if isinstance(output, tuple) else output
            captured[layer_index] = hidden[0].detach().float().cpu().numpy()
        return hook

    for layer_index in selected:
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
    if set(captured) != set(selected):
        raise RuntimeError("未捕获全部指定层的 Hidden States")
    return selected, [captured[index] for index in selected]


def analyze_windows(
    windows: list[list[int]],
    prompt_length: int,
    layer_outputs: list[np.ndarray],
    layer_indices: list[int],
    threshold: float,
) -> dict[str, Any]:
    if not windows:
        return {
            "measurement_status": "insufficient_fixed_windows",
            "window_count": 0,
            "aggregate": None,
            "per_layer": None,
        }
    prediction_windows = [
        [prompt_length + token_index - 1 for token_index in window]
        for window in windows
    ]
    per_layer = []
    for layer_index, layer_output in zip(layer_indices, layer_outputs):
        centroids = np.stack([
            normalize(layer_output[positions].mean(axis=0))
            for positions in prediction_windows
        ])
        metrics = convergence_metrics(centroids, threshold)
        metrics["layer_index_zero_based"] = layer_index
        per_layer.append(metrics)
    return {
        "measurement_status": "available",
        "window_count": len(windows),
        "aggregate": aggregate_layer_metrics(per_layer),
        "per_layer": per_layer,
    }


def analyze_item(
    item: dict[str, Any],
    model: Any,
    tokenizer: Any,
    device: torch.device,
    args: argparse.Namespace,
) -> dict[str, Any]:
    base = {"task_id": item.get("task_id"), "task_type": item.get("task_type")}
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
    encoded = tokenizer(raw, add_special_tokens=False, return_offsets_mapping=True)
    content_ids = [int(value) for value in encoded["input_ids"]]
    offsets = [(int(left), int(right)) for left, right in encoded["offset_mapping"]]
    if generated_ids[:len(content_ids)] != content_ids:
        return {**base, "status": "error", "error": "token round-trip mismatch"}

    parsed = item.get("parsed_output") if isinstance(item.get("parsed_output"), dict) else {}
    field_spans = top_level_value_spans(raw)
    field_indices: dict[str, list[int]] = {}
    alignment_failures: dict[str, int] = {}
    for field in DIMENSIONS:
        if field not in field_spans or field not in parsed:
            field_indices[field] = []
            alignment_failures[field] = 0
            continue
        leaf_spans, failures = locate_leaf_spans(raw, field_spans[field], parsed[field])
        field_indices[field] = token_indices_for_spans(offsets, leaf_spans)
        alignment_failures[field] = failures

    all_content_indices = sorted({
        index for indices in field_indices.values() for index in indices
    })
    full_ids = [int(value) for value in prompt_ids + generated_ids]
    layer_indices, layer_outputs = collect_selected_layers(
        model, full_ids, device, args.last_layers
    )

    overall_windows = select_fixed_windows(
        all_content_indices,
        args.window_size,
        args.minimum_windows,
        args.maximum_windows,
    )
    overall = analyze_windows(
        overall_windows,
        len(prompt_ids),
        layer_outputs,
        layer_indices,
        args.convergence_threshold,
    )

    dimensions = {}
    for field in DIMENSIONS:
        windows = select_fixed_windows(
            field_indices[field],
            args.window_size,
            args.minimum_windows,
            args.maximum_windows,
        )
        measurement = analyze_windows(
            windows,
            len(prompt_ids),
            layer_outputs,
            layer_indices,
            args.convergence_threshold,
        )
        measurement["content_token_count"] = len(field_indices[field])
        measurement["leaf_alignment_failures"] = alignment_failures[field]
        dimensions[field] = measurement

    return {
        **base,
        "observation_source": "hidden_state_vector_convergence",
        "overall_convergence": overall,
        "dimension_convergence": dimensions,
        "diagnostics": {
            "strict_json_valid": bool(item.get("parser", {}).get("strict_json_valid")),
            "prompt_tokens": len(prompt_ids),
            "generated_tokens": len(generated_ids),
            "content_tokens": len(all_content_indices),
            "selected_layer_indices_zero_based": layer_indices,
        },
        "status": "success",
        "error": "",
    }


def main() -> None:
    args = parse_args()
    if args.window_size < 2:
        raise ValueError("window-size 至少为 2")
    if args.minimum_windows < 3:
        raise ValueError("minimum-windows 至少为 3")
    if args.maximum_windows < args.minimum_windows:
        raise ValueError("maximum-windows 不能小于 minimum-windows")
    if not 0.0 < args.convergence_threshold < 1.0:
        raise ValueError("convergence-threshold 必须位于 (0, 1)")

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
        raise RuntimeError("内容 token 对齐需要 fast tokenizer")
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
            results.append(analyze_item(item, model, tokenizer, device, args))
        except Exception as exc:
            results.append({
                "task_id": item.get("task_id"),
                "task_type": item.get("task_type"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    write_json(Path(args.output_file), {
        "metadata": {
            "method": "structured_evidence_hidden_state_convergence",
            "stage": "independent_hidden_state_convergence_track",
            "source": args.input_file,
            "model_path": args.model_path,
            "uses_llm_judge_outputs": False,
            "fused_with_llm_judge": False,
            "uses_training": False,
            "uses_answer_correctness": False,
            "generates_final_answer": False,
            "analyzes_token_identity_changes": False,
            "analyzes_hidden_vector_sequence": True,
            "content_alignment": "substantive JSON leaf values only; fixed syntax excluded",
            "window_size": args.window_size,
            "minimum_windows": args.minimum_windows,
            "maximum_windows": args.maximum_windows,
            "last_layers": args.last_layers,
            "convergence_threshold": args.convergence_threshold,
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
