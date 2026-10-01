"""Reasoning capture (for the mode-11 Consistency oracle).

Verified (C4): stock logs contain code + stdout, NOT the model's natural-language reasoning. A scaffold
dumps per-interaction messages to `logs/messages.jsonl`; here we read them and align to the
`environment_io` interactions (by interaction number) so the Consistency oracle has reasoning per step.
"""
from __future__ import annotations

import json
import os
from typing import Any


def write_messages(path: str, messages: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")


def read_messages(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    out: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def reasoning_for_interaction(messages: list[dict[str, Any]], interaction: Any) -> str:
    return " ".join(str(m.get("text", "")) for m in messages if m.get("interaction") == interaction)


def align_to_trajectory(
    messages: list[dict[str, Any]], interactions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    aligned: list[dict[str, Any]] = []
    for it in interactions:
        num = it.get("number")
        try:
            n: Any = int(float(num))
        except (TypeError, ValueError):
            n = num
        aligned.append({**it, "reasoning": reasoning_for_interaction(messages, n)})
    return aligned


def all_reasoning_text(messages: list[dict[str, Any]]) -> str:
    return " ".join(str(m.get("text", "")) for m in messages)
