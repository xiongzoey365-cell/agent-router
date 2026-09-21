#!/usr/bin/env python3
"""Rerun only length-truncated full-answer records and rebuild JSON/Markdown."""

import json
from datetime import datetime, timezone
from pathlib import Path

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams


ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "outputs/full_answers_qwen3_8b/full_answers.json"
MD_PATH = ROOT / "outputs/full_answers_qwen3_8b/full_answers.md"
MODEL_PATH = "/home/xiongziyan/.cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218"


def render_markdown(payload: dict) -> str:
    exp = payload["experiment"]
    lines = [
        "# Qwen3-8B 全答案生成结果",
        "",
        f"- 模型：`{exp['model_path']}`",
        f"- 解码：temperature={exp['temperature']}，Thinking={exp['thinking']}",
        f"- 样本数：{exp['sample_count']}",
        "- 本文件只记录生成结果，不进行答案质量评分。",
        "",
    ]
    for i, item in enumerate(payload["results"], 1):
        lines.extend(
            [
                f"## {i}. {item['task_id']}",
                "",
                f"- 类型：`{item['task_type']}`",
                f"- 数据集难度：L{item['difficulty_level']}",
                f"- 生成 token：{item['generated_tokens']}",
                f"- 结束原因：`{item['finish_reason']}`",
                "",
                "### 题目",
                "",
                item["prompt"],
                "",
                "### 生成答案",
                "",
                item["generated_answer"],
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    targets = [x for x in payload["results"] if x.get("finish_reason") == "length"]
    if not targets:
        print("No length-truncated records found.")
        return

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    prompts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": item["prompt"]}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        for item in targets
    ]

    llm = LLM(
        model=MODEL_PATH,
        trust_remote_code=True,
        max_model_len=16384,
        gpu_memory_utilization=0.90,
        tensor_parallel_size=1,
    )
    params = SamplingParams(temperature=0.0, max_tokens=8192)
    outputs = llm.generate(prompts, params)

    by_id = {item["task_id"]: item for item in payload["results"]}
    for source, request_output in zip(targets, outputs):
        generated = request_output.outputs[0]
        record = by_id[source["task_id"]]
        record["generated_answer"] = generated.text
        record["generated_tokens"] = len(generated.token_ids)
        record["finish_reason"] = generated.finish_reason
        record["stop_reason"] = generated.stop_reason
        print(source["task_id"], len(generated.token_ids), generated.finish_reason)

    payload["experiment"]["max_tokens"] = 8192
    payload["experiment"]["max_model_len"] = 16384
    payload["experiment"]["rerun_at"] = datetime.now(timezone.utc).isoformat()
    payload["experiment"]["rerun_scope"] = [x["task_id"] for x in targets]
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
