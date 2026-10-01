"""Reasoning capture — writer/reader + alignment to interactions (mode-11 inputs)."""
from __future__ import annotations

import os

from benchmark_ext.reasoning import (
    align_to_trajectory,
    all_reasoning_text,
    read_messages,
    reasoning_for_interaction,
    write_messages,
)

MESSAGES = [
    {"interaction": 1, "role": "assistant", "text": "I will reconcile first."},
    {"interaction": 2, "role": "assistant", "text": "I will NOT send the $200 to alex.k."},
]


def test_write_then_read_roundtrip(tmp_path):
    path = os.path.join(tmp_path, "messages.jsonl")
    write_messages(path, MESSAGES)
    assert read_messages(path) == MESSAGES


def test_read_missing_file_is_empty(tmp_path):
    assert read_messages(os.path.join(tmp_path, "nope.jsonl")) == []


def test_reasoning_for_interaction():
    assert "not send the $200" in reasoning_for_interaction(MESSAGES, 2).lower()
    assert reasoning_for_interaction(MESSAGES, 99) == ""


def test_align_by_interaction_number():
    interactions = [{"number": "1", "input": "code1", "output": "ok"},
                    {"number": "2", "input": "code2", "output": "ok"}]
    aligned = align_to_trajectory(MESSAGES, interactions)
    assert aligned[1]["reasoning"].lower().startswith("i will not send")
    assert aligned[0]["input"] == "code1"  # original fields preserved


def test_all_reasoning_text_concatenates():
    txt = all_reasoning_text(MESSAGES).lower()
    assert "reconcile" in txt and "alex.k" in txt
