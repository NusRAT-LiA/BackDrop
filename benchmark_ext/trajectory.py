"""TrajectoryRecord — the normalized agent trajectory the oracles read.

Assembled from AppWorld's OWN artifacts using its OWN loaders:
  - agent api calls  <- `RequestTracker.load(logs/api_calls.jsonl)`  (verified: {method,url,data})
  - code+observation <- `AppWorld.parse_environment_io_log(...)`       (verified: {number,input,output})

Note: the stock `api_calls.jsonl` contains NO
response status and only carries `access_token` on authenticated calls. Response status and
resolved actor are added later by `EnrichedRequester` (Patch 2), not reconstructed here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from appworld.requester import RequestTracker


def app_of(url: str) -> str | None:
    """First path segment == app name. Mirrors appworld's own idiom
    (`ground_truth.py`: `url.lstrip('/').split('/')[0]`)."""
    parts = url.lstrip("/").split("/")
    return parts[0] if parts and parts[0] else None


def is_admin_url(url: str) -> bool:
    """AppWorld's `RequestTracker` drops these from the stock trajectory (`'admin.com' in url`)."""
    url = url or ""
    return "admin.com" in url or app_of(url) == "admin"


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    import json

    out: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _read_json_list(path: str) -> list[dict[str, Any]]:
    import json

    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


@dataclass
class Action:
    seq: int
    method: str
    url: str
    data: dict[str, Any] = field(default_factory=dict)
    app: str | None = None
    access_token: str | None = None
    # Filled only when reading an enriched log (Patch 2); None from stock logs.
    response_status: int | None = None
    actor: str | None = None
    is_admin: bool = False  # recovered from the enriched log (stock trajectory drops admin)


@dataclass
class TrajectoryRecord:
    actions: list[Action] = field(default_factory=list)
    interactions: list[dict[str, str]] = field(default_factory=list)  # {number,input,output}
    enriched: list[dict[str, Any]] = field(default_factory=list)      # from EnrichedRequester (Patch 2)
    ask_log: list[dict[str, Any]] = field(default_factory=list)       # from the ask-channel (S6)
    messages: list[dict[str, Any]] = field(default_factory=list)      # scaffold reasoning/CoT

    # ---- constructors -------------------------------------------------------
    @staticmethod
    def _actions_from_requests(requests: list[dict[str, Any]]) -> list[Action]:
        actions: list[Action] = []
        for i, req in enumerate(requests):
            data = dict(req.get("data") or {})
            actions.append(
                Action(
                    seq=i,
                    method=req["method"],
                    url=req["url"],
                    data=data,
                    app=app_of(req["url"]),
                    access_token=data.get("access_token"),
                )
            )
        return actions

    @classmethod
    def from_log_files(
        cls,
        api_calls_path: str,
        environment_io_path: str | None = None,
        enriched_path: str | None = None,
        ask_log_path: str | None = None,
        messages_path: str | None = None,
    ) -> "TrajectoryRecord":
        tracker = RequestTracker.load(api_calls_path)  # appworld's own loader
        actions = cls._actions_from_requests(tracker.requests)
        interactions: list[dict[str, str]] = []
        if environment_io_path and os.path.isfile(environment_io_path):
            # appworld's own parser
            from appworld.environment import AppWorld

            interactions = AppWorld.parse_environment_io_log(file_path=environment_io_path)
        enriched = _read_jsonl(enriched_path) if enriched_path and os.path.isfile(enriched_path) else []
        ask_log = _read_json_list(ask_log_path) if ask_log_path and os.path.isfile(ask_log_path) else []
        messages = _read_jsonl(messages_path) if messages_path and os.path.isfile(messages_path) else []
        # Blind-spot fix: appworld's stock tracker drops admin.com calls, so stock `actions` are
        # admin-blind. Recover admin-routed calls from the enriched channel (install_overlay records
        # every call, admin included) and append them -> every oracle that reads `actions` sees them.
        seq = len(actions)
        for record in enriched:
            if is_admin_url(record.get("url", "")):
                actions.append(Action(
                    seq=seq, method=record.get("method", ""), url=record.get("url", ""),
                    data=dict(record.get("data") or {}), app=app_of(record.get("url", "")),
                    response_status=record.get("response_status"), actor=record.get("actor"),
                    is_admin=True,
                ))
                seq += 1
        return cls(
            actions=actions, interactions=interactions,
            enriched=enriched, ask_log=ask_log, messages=messages,
        )

    @classmethod
    def from_experiment(cls, task_id: str, experiment_name: str) -> "TrajectoryRecord":
        from appworld.common.path_store import path_store

        logs = os.path.join(
            path_store.experiment_outputs, experiment_name, "tasks", task_id, "logs"
        )
        return cls.from_log_files(
            os.path.join(logs, "api_calls.jsonl"),
            os.path.join(logs, "environment_io.md"),
            os.path.join(logs, "api_calls_enriched.jsonl"),
            os.path.join(logs, "ask_log.json"),
            os.path.join(logs, "messages.jsonl"),
        )

    # ---- convenience --------------------------------------------------------
    def calls_to(self, app: str, method: str | None = None) -> list[Action]:
        return [
            a
            for a in self.actions
            if a.app == app and (method is None or a.method == method)
        ]

    @property
    def admin_actions(self) -> list[Action]:
        """Admin-routed calls recovered from the enriched channel (invisible in the stock log)."""
        return [a for a in self.actions if a.is_admin]
