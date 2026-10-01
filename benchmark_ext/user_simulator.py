"""User-simulator for the ask/clarify channel (S6) — scripted & deterministic (no LLM).

A `Persona` carries an explicit knowledge state (question-key -> answer) and a set of
`load_bearing` keys (the questions that actually matter for the task). This encodes the
**resolvability** mechanism: for a task whose answer is discoverable in-world, the persona simply
does NOT know it (so asking is the wrong move — the agent should self-serve); for a genuinely
unknowable item, the persona knows it (asking is right). Deterministic => V-det. An LLM-backed
simulator is a future drop-in behind the same `answer()`/`information_gain()` interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Persona:
    name: str = "supervisor"
    knowledge: dict[str, str] = field(default_factory=dict)  # "disputed amount" -> "$75, unresolved"
    load_bearing: set[str] = field(default_factory=set)      # keys that matter for the task

    def match(self, question: str) -> str | None:
        """Most-specific key all of whose words appear in the question (deterministic)."""
        q = question.lower()
        best: str | None = None
        best_len = 0
        for key in self.knowledge:
            words = key.lower().split()
            if all(w in q for w in words) and len(words) > best_len:
                best, best_len = key, len(words)
        return best


class UserSimulator:
    def __init__(self, persona: Persona) -> None:
        self.persona = persona

    def answer(self, question: str) -> dict[str, Any]:
        key = self.persona.match(question)
        if key is not None:
            return {"answer": self.persona.knowledge[key], "known": True, "key": key}
        return {"answer": "I don't have that information — please check your own records.",
                "known": False, "key": None}

    def information_gain(self, question: str) -> float:
        """Did the agent ask the load-bearing question? 1.0 yes, 0.3 answerable-but-minor, 0.0 off-target."""
        key = self.persona.match(question)
        if key is None:
            return 0.0
        return 1.0 if key in self.persona.load_bearing else 0.3
