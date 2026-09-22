#!/usr/bin/env python3
"""Measure non-local recurrence in the six-dimension output hidden states."""

from __future__ import annotations

import argparse
import gc
import json
import zlib
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F


HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "outputs" / "six_dimension"
DEFAULT_OUTPUT = HERE / "difficulty_signal_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-gap", type=int, default=32)
    parser.add_argument("--similarity-threshold", type=float, default=0.95)
    return parser.parse_args()


def nonlocal_recurrence(
    states: torch.Tensor,
    minimum_gap: int,
    threshold: float,
) -> dict[str, float]:
    normalized = F.normalize(states.float(), dim=-1)
    similarity = normalized @ normalized.T
    count = normalized.shape[0]
    positions = torch.arange(count)
    valid = (positions[:, None] - positions[None, :]).abs() >= minimum_gap
    maxima = similarity.masked_fill(~valid, -2).max(dim=1).values
    maxima = maxima[maxima > -1]
    result = {
        "mean_nonlocal_max_cosine": float(maxima.mean()),
        "p95_nonlocal_max_cosine": float(torch.quantile(maxima, 0.95)),
        "rate_above_threshold": float((maxima > threshold).float().mean()),
    }
    del normalized, similarity, positions, valid, maxima
    return result


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    layer_rows: list[dict[str, Any]] = []
    selected_layers = [0, 6, 12, 18, 24, 30, 34, 36]

    for record_path in sorted((input_dir / "records").glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        hidden_path = input_dir.parent / record["artifacts"]["raw_hidden_states"]
        artifact = torch.load(hidden_path, map_location="cpu", weights_only=False)
        generated_count = int(artifact["generated_token_count"])
        if record["generation"]["termination"] == "eos":
            generated_count -= 1
        start = int(artifact["prompt_token_count"])
        end = start + generated_count
        states = artifact["hidden_states"]

        final_metrics = nonlocal_recurrence(
            states[-1][0, start:end], args.minimum_gap, args.similarity_threshold
        )
        token_ids = record["generated_token_ids"][:generated_count]
        fourgrams = list(zip(token_ids, token_ids[1:], token_ids[2:], token_ids[3:]))
        encoded_text = record["raw_output"].encode("utf-8")
        row = {
            "task_id": record["task_id"],
            "task_type": record["task_type"],
            "visible_generated_tokens": generated_count,
            **final_metrics,
            "token_4gram_uniqueness": len(set(fourgrams)) / max(1, len(fourgrams)),
            "zlib_compression_ratio": len(zlib.compress(encoded_text, level=9)) / max(1, len(encoded_text)),
        }
        rows.append(row)

        if record["task_type"] == "logical_reasoning":
            for layer in selected_layers:
                metrics = nonlocal_recurrence(
                    states[layer][0, start:end], args.minimum_gap, args.similarity_threshold
                )
                layer_rows.append({"task_id": record["task_id"], "layer": layer, **metrics})

        print(f"analyzed {record['task_id']}", flush=True)
        del artifact, states
        gc.collect()

    (output_dir / "six_dimension_recurrence.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "logic_layer_recurrence.json").write_text(
        json.dumps(layer_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
