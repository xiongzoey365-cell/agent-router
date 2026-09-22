#!/usr/bin/env python3
"""Build reproducible six-dimension-only distribution and outlier metrics."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ANALYSIS_DIR = HERE / "difficulty_signal_analysis"
TEXT_FEATURES = (
    "visible_generated_tokens",
    "verification_mentions",
    "uncertainty_mentions",
    "absence_mentions",
)
HIDDEN_FEATURES = (
    "temporal_distance_mean",
    "temporal_terminal_to_early_ratio",
    "late8_depth_update_mean",
    "late8_depth_update_terminal",
)
RECURRENCE_FEATURES = (
    "mean_nonlocal_max_cosine",
    "p95_nonlocal_max_cosine",
    "rate_above_threshold",
)


def zscore_within_type(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["task_type"]].append(row)
    for group in groups.values():
        for field in fields:
            values = np.asarray([float(row[field]) for row in group], dtype=np.float64)
            std = float(values.std(ddof=0))
            scores = np.zeros_like(values) if std < 1e-12 else (values - values.mean()) / std
            for row, score in zip(group, scores, strict=True):
                row[f"z_{field}"] = float(score)


def rms_z(row: dict[str, Any], fields: tuple[str, ...]) -> float:
    return math.sqrt(sum(row[f"z_{field}"] ** 2 for field in fields) / len(fields))


def high_dispersion_threshold(values: list[float]) -> float:
    # With only five tasks per type, flag the upper decile as descriptive
    # high-dispersion points; this is not an inferential outlier test.
    return float(np.quantile(np.asarray(values, dtype=np.float64), 0.90))


def main() -> None:
    metrics = json.loads((ANALYSIS_DIR / "metrics.json").read_text(encoding="utf-8"))
    recurrence = json.loads(
        (ANALYSIS_DIR / "six_dimension_recurrence.json").read_text(encoding="utf-8")
    )
    six_rows = [dict(row) for row in metrics if row["arm"] == "six_dimension"]
    recurrence_by_id = {row["task_id"]: row for row in recurrence}
    for row in six_rows:
        source = recurrence_by_id[row["task_id"]]
        row.update({"mean_nonlocal_max_cosine": source["mean_nonlocal_max_cos"], "p95_nonlocal_max_cosine": source["p95_nonlocal_max_cos"], "rate_above_threshold": source["rate_max_cos_gt_095"]})
        row["token_4gram_uniqueness"] = source["token_4gram_unique"]
        row["zlib_compression_ratio"] = source["zlib_ratio"]

    zscore_within_type(six_rows, TEXT_FEATURES + HIDDEN_FEATURES + RECURRENCE_FEATURES)
    for row in six_rows:
        row["text_anomaly"] = rms_z(row, TEXT_FEATURES)
        row["hidden_anomaly"] = rms_z(row, HIDDEN_FEATURES)
        row["combined_anomaly"] = math.hypot(
            row["text_anomaly"], row["hidden_anomaly"]
        ) / math.sqrt(2.0)
        row["text_semantic_cue_anomaly"] = rms_z(row, TEXT_FEATURES[1:])
        row["hidden_late_dynamics_anomaly"] = rms_z(row, HIDDEN_FEATURES[1:])
        row["recurrence_anomaly"] = rms_z(row, RECURRENCE_FEATURES)

    fences = {
        "combined_anomaly": high_dispersion_threshold([row["combined_anomaly"] for row in six_rows]),
        "text_anomaly": high_dispersion_threshold([row["text_anomaly"] for row in six_rows]),
        "hidden_anomaly": high_dispersion_threshold([row["hidden_anomaly"] for row in six_rows]),
        "recurrence_anomaly": high_dispersion_threshold([row["recurrence_anomaly"] for row in six_rows]),
    }
    for row in six_rows:
        row["outlier"] = {
            metric: bool(row[metric] >= fence) for metric, fence in fences.items()
        }

    compact_fields = (
        "task_id", "task_type", "difficulty_level",
        "text_anomaly", "hidden_anomaly", "combined_anomaly",
        "z_visible_generated_tokens", "z_verification_mentions",
        "z_uncertainty_mentions", "z_absence_mentions", "text_semantic_cue_anomaly",
        "z_temporal_distance_mean", "z_temporal_terminal_to_early_ratio",
        "z_late8_depth_update_mean", "z_late8_depth_update_terminal",
        "hidden_late_dynamics_anomaly", "mean_nonlocal_max_cosine",
        "p95_nonlocal_max_cosine", "rate_above_threshold",
        "token_4gram_uniqueness", "zlib_compression_ratio",
        "recurrence_anomaly", "outlier",
    )
    output = {
        "scope": "outputs/six_dimension only",
        "standardization": "population z-score within each five-task type",
        "outlier_rule": "panel score >= the 90th percentile across the 25 standardized task scores; descriptive highlight, not an inferential outlier test",
        "fences": fences,
        "rows": [{key: row[key] for key in compact_fields} for row in six_rows],
    }
    target = ANALYSIS_DIR / "six_dimension_visualization_data.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    for metric in fences:
        flagged = [row["task_id"] for row in six_rows if row["outlier"][metric]]
        print(f"{metric}: fence={fences[metric]:.6f}; flagged={flagged}")


if __name__ == "__main__":
    main()
