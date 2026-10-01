"""run: run an agent over the standing tasks and keep everything (benchmark_ext/store.py).

    python -m benchmark_ext.run --tasks compounds,twins                   # pass 1: skip what is done, run the rest
    python -m benchmark_ext.run --tasks compounds --workers 2 --limit 10  # a few, two at a time
    python -m benchmark_ext.run --sample 300 --workers 256 \              # smoke test: the same 300 tasks for every
        --model bedrock/us.anthropic.claude-opus-5                        #   model, 256 at a time
    python -m benchmark_ext.run --regrade --tasks compounds               # regrade stored runs with the current graders
    python -m benchmark_ext.run --index                                   # rebuild results/index.jsonl and print the summary

Models route through litellm by name prefix. `bedrock/<model id>` signs with the ambient AWS credentials
(AWS_PROFILE or an instance role) and needs no key; `--aws-region` picks the region. A service fault (rate
limit, throttle, 5xx, timeout) is retried without limit until `--retry-budget`; a request fault (context
window, auth, validation) is recorded and raised at once.

Every run is its own process (AppWorld caches a task per process, and keeps one in-memory end state per
task id), with its own composed root under .tmp/runs/, moved into results/ when it ends. A run is skipped
when its verdict exists, so a stopped pass resumes where it left off. The model key is read from the
environment or from .env by name; it is never printed and never stored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta as _timedelta
from datetime import timezone
from typing import Any

from benchmark_ext import store
from benchmark_ext.generate.tasks.task_generators.base import PROJECT, compose_root

# Each run builds a whole composed world here (app databases, logs, hundreds of small files) and only the
# finished output is moved into results/. On a shared filesystem that churn is the bottleneck: on Lustre it put
# 309 of 600 task processes into uninterruptible I/O wait, more than were on CPU. Point AW_SCRATCH at local
# disk to keep it off the network; the default is unchanged.
SCRATCH = os.environ.get("AW_SCRATCH") or os.path.join(PROJECT, ".tmp", "runs")
DEFAULT_MODEL = "gemini/gemini-flash-latest"


PROVIDER_KEYS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY",
                 "deepseek": "DEEPSEEK_API_KEY", "groq": "GROQ_API_KEY", "together_ai": "TOGETHER_API_KEY", "xai": "XAI_API_KEY",
                 "moonshot": "MOONSHOT_API_KEY", "mistral": "MISTRAL_API_KEY"}
# Providers that need no key at all: bedrock and vertex sign with the ambient cloud credentials, the rest are
# models you serve yourself and reach with --api-base.
KEYLESS_PROVIDERS = ("bedrock", "sagemaker", "vertex_ai", "hosted_vllm", "ollama", "ollama_chat", "vllm", "lm_studio")

# A model call is worth retrying when the fault is the service's, not the request's. Unlimited, because a
# throttled pass that gives up wastes the whole run; the wall-clock budget below is the only stop.
RETRYABLE_LLM = ("ratelimit", "throttl", "toomanyrequests", "serviceunavailable", "internalserver",
                 "internalerror", "timeout", "apiconnection", "overloaded", "modelnotready", "503", "502",
                 "504", "429", "connectionerror", "remotedisconnected", "incompleteread",
                 # a lapsed token is transient: botocore refreshes it on the next attempt
                 "expiredtoken", "tokenexpired")
# The subset of RETRYABLE_LLM that outranks FATAL_LLM, because a provider may report a rate limit inside an
# exception class that otherwise reads as a bad request. Kept narrow: only signals that mean "too many, too fast".
RATE_LIMIT_LLM = ("429", "ratelimit", "rate_limit", "toomanyrequests", "resource_exhausted", "resourceexhausted",
                  "exceededyourcurrentquota", "quotaexceeded")
# The request itself is wrong; retrying sends the same bad request again. Recorded, never retried.
FATAL_LLM = ("contextwindow", "context_length", "contextlength", "too long", "maximum context",
             "authentication", "permission", "accessdenied", "notfound", "badrequest", "invalidrequest",
             "unsupported", "validation")
# The subset of FATAL_LLM that is the MODEL's own ceiling rather than our setup being wrong. Only these are
# graded on the partial trajectory: the run is a real capability result. The rest (auth, permission, notfound)
# mean the harness is misconfigured, so grading them would score our mistake as the model's failure.
MODEL_LIMIT_FATAL = ("contextwindow", "context_length", "contextlength", "too long", "maximum context")


def is_model_limit(exc: BaseException) -> bool:
    blob = f"{type(exc).__name__} {exc}".lower().replace(" ", "")
    return any(k.replace(" ", "") in blob for k in MODEL_LIMIT_FATAL)


def provider_key_var(model: str) -> str | None:
    """The environment variable litellm reads for this model's provider (the prefix before '/'; a bare name is
    OpenAI's). None for a provider that needs no key: a locally served model, or bedrock, which signs with the
    ambient AWS credentials (AWS_PROFILE / instance role) instead of a key.

    A provider we have not named falls back to litellm's own convention, `<PREFIX>_API_KEY`, so any of its
    providers can be reached from .env without editing this file."""
    prefix = model.split("/")[0] if "/" in model else "openai"
    if prefix in PROVIDER_KEYS:
        return PROVIDER_KEYS[prefix]
    return None if prefix in KEYLESS_PROVIDERS else f"{prefix.upper().replace('-', '_')}_API_KEY"


def raw_dump(resp: Any, limit: int = 20000) -> Any:
    """A JSON-safe copy of the provider's whole reply, kept only when the parsed content came back empty.

    Without it an empty reply is unattributable: a model that genuinely returned nothing looks identical to
    one whose text arrived in a channel litellm did not surface (claude-sonnet-5 billed 168 completion tokens
    for an empty content and an absent reasoning_content). `default=str` because some providers return bytes.
    """
    for as_dict in (lambda: resp.model_dump(), lambda: resp.dict(), lambda: dict(resp)):
        try:
            return json.loads(json.dumps(as_dict(), default=str))
        except Exception:
            continue
    return str(resp)[:limit]


def classify_llm_error(exc: BaseException) -> str:
    """`retry` (service fault, retry forever), `fatal` (our request is wrong), or `unknown` (retry, bounded).

    Matched on the exception class name and message together, because litellm wraps provider errors in its own
    classes and the useful signal is sometimes only in the text.
    """
    blob = f"{type(exc).__name__} {exc}".lower().replace(" ", "")
    # Checked before FATAL_LLM: a credential refresh that fails carries text ("unsupported protocol scheme")
    # that matches FATAL_LLM's "unsupported", so the request looked malformed when the transport was at fault.
    if any(k in blob for k in ("retrievingcredentials", "refreshthecredentials", "custom-process", "customprocess")):
        return "retry"
    # Also before FATAL_LLM. A rate limit is transient however it is wrapped, and gemini wraps quota exhaustion
    # in a BadRequestError whose body carries the 429. FATAL's "badrequest" matched the class name first, so the
    # run was abandoned on a fault that a retry clears: 313 gemini-3.8-flash runs died this way.
    if any(k in blob for k in RATE_LIMIT_LLM):
        return "retry"
    if any(k.replace(" ", "") in blob for k in FATAL_LLM):
        return "fatal"
    if any(k.replace(" ", "") in blob for k in RETRYABLE_LLM):
        return "retry"
    return "unknown"


def load_provider_key(model: str) -> str | None:
    var = provider_key_var(model)
    if var:
        load_env_key(var)
    return var


def load_env_key(name: str) -> None:
    """Read `name` from <project>/.env by name if it is not in the environment (tolerates `export`, spaces,
    quotes). Never sources the file and never prints the value."""
    if os.environ.get(name):
        return
    path = os.path.join(PROJECT, ".env")
    if not os.path.isfile(path):
        return
    import re

    pat = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*?)\s*$")
    for line in open(path, encoding="utf-8", errors="replace"):
        m = pat.match(line.rstrip("\r\n"))
        if m and m.group(1).strip().strip('"').strip("'"):
            os.environ[name] = m.group(1).strip().strip('"').strip("'")
            return


def keep_aws_clock_real() -> None:
    """AppWorld freezes the clock to the task's simulated date (freezegun). AWS SigV4 signs with the current
    time, so under the freeze every bedrock request is signed in 2023 and rejected with `Signature expired`.

    freezegun's ignore list cannot help: it replaces the class inside the `datetime` module, which botocore
    reads through. So point botocore's own clock at the real one instead. The task's clock stays frozen, which
    is what the benchmark needs. Idempotent, and a no-op when neither library is installed.
    """
    try:
        from freezegun.api import real_datetime
    except Exception:
        return
    try:
        from botocore import auth, compat, credentials, endpoint, signers
    except Exception:
        return

    def real_now(remove_tzinfo: bool = True):
        now = real_datetime.now(timezone.utc)
        return now.replace(tzinfo=None) if remove_tzinfo else now

    for mod in (compat, auth, signers, endpoint):
        if getattr(mod, "get_current_datetime", None) is not None:
            mod.get_current_datetime = real_now

    # Credential refresh is a second, separate clock: `_local_now()` calls datetime.datetime.now(), so a
    # frozen clock compares a 2026 expiry against 2023, concludes there is plenty of time, and never
    # refreshes. Swapping the module's `datetime` name reaches it, because `_local_now` looks the name up at
    # call time, whereas rebinding `_local_now` would miss the copies already bound as default arguments.
    class _RealDatetimeModule:
        datetime = real_datetime
        timedelta = _timedelta

    credentials.datetime = _RealDatetimeModule


def _real_clock() -> tuple[Any, Any]:
    """AppWorld freezes time for the task clock (freezegun); the model calls are timed on the real clock."""
    try:
        from freezegun.api import real_datetime, real_time

        return real_time, lambda: real_datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return time.time, store.now


class LoggedLLM:
    """`llm(messages) -> str` over litellm that records every call twice over: metrics in `self.calls`
    (latency, tokens, finish reason, prompt hash) and the verbatim prompt and reply in `self.io`, so a pass
    this expensive is analysable later without paying for generation again.

    Retries a service fault (rate limit, throttle, 5xx, timeout) without limit, bounded only by
    `retry_budget_s`; a request fault (context window, auth, validation) is recorded and raised at once.
    """

    def __init__(self, model: str, temperature: float | None = 0.0, timeout: float = 180.0, retries: int = 5, max_tokens: int | None = None,
                 api_base: str | None = None, aws_region: str | None = None, retry_budget_s: float = 1800.0, keep_io: bool = True):
        self.model, self.temperature, self.timeout, self.retries, self.max_tokens = model, temperature, timeout, retries, max_tokens
        self.api_base, self.aws_region, self.retry_budget_s, self.keep_io = api_base, aws_region, retry_budget_s, keep_io
        self.calls: list[dict[str, Any]] = []
        self.io: list[dict[str, Any]] = []
        self._time, self._now = _real_clock()

    def __call__(self, messages: list[dict[str, Any]]) -> str:
        import litellm

        # temperature=None means send no temperature at all: reasoning models reject any value but their own
        # default, and AppWorld's own configs likewise run reasoning models without pinning it.
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "timeout": self.timeout}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.model.startswith("bedrock/") and self.aws_region:
            kwargs["aws_region_name"] = self.aws_region   # bedrock signs per region; litellm needs it explicitly
        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        digest = hashlib.sha1("\n".join(f"{m['role']}:{m.get('content') or ''}" for m in messages).encode()).hexdigest()[:12]
        i = len(self.io) + 1
        attempt, delay, started, errors = 0, 5.0, self._time(), []
        while True:
            attempt += 1
            t0 = self._time()
            try:
                resp = litellm.completion(**kwargs)
                break
            except Exception as exc:
                kind = classify_llm_error(exc)
                rec = {"i": len(self.calls) + 1, "call": i, "at": self._now(), "error": type(exc).__name__, "error_kind": kind,
                       "detail": str(exc)[:300], "retry": attempt - 1, "latency_s": round(self._time() - t0, 2)}
                self.calls.append(rec)
                errors.append({k: rec[k] for k in ("error", "error_kind", "detail", "latency_s")})
                spent = self._time() - started
                giving_up = kind == "fatal" or spent > self.retry_budget_s or (kind == "unknown" and attempt > self.retries)
                if giving_up:
                    if self.keep_io:
                        self.io.append({"call": i, "at": self._now(), "ok": False, "error_kind": kind, "attempts": attempt,
                                        "errors": errors, "messages": messages, "response": None})
                    raise
                # say it out loud: an unlimited retry that sleeps in silence looks identical to a hang
                print(f"[llm retry] call {i} attempt {attempt} {kind} {type(exc).__name__}: {str(exc)[:160]} "
                      f"(sleeping {delay:.0f}s, {spent:.0f}s of {self.retry_budget_s:.0f}s spent)",
                      file=sys.stderr, flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        usage = getattr(resp, "usage", None)
        choice = resp.choices[0]
        text = choice.message.content or ""
        finish = getattr(choice, "finish_reason", None)
        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        # gpt-oss returns its whole turn in reasoning_content and leaves content empty (39 of 48 calls on
        # gpt-oss-20b). An empty string tells the agent nothing and burns a step, so fall back to the thinking
        # text; both fields stay in llm_io.jsonl so a reader can still tell which channel it came from.
        salvaged = False
        if not text.strip() and reasoning.strip():
            text, salvaged = reasoning, True
        metrics = {
            "i": len(self.calls) + 1, "call": i, "at": self._now(), "latency_s": round(self._time() - t0, 2), "model": getattr(resp, "model", self.model),
            "prompt_tokens": getattr(usage, "prompt_tokens", None), "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None), "finish_reason": finish,
            "prompt_chars": prompt_chars, "prompt_sha1": digest, "response_chars": len(text),
            "attempts": attempt, "retries": attempt - 1, "empty_response": not text.strip(),
            "content_from_reasoning": salvaged,
        }
        self.calls.append(metrics)
        if self.keep_io:
            record = {"call": i, "at": self._now(), "ok": True, "attempts": attempt, "errors": errors,
                      "finish_reason": finish, "prompt_tokens": metrics["prompt_tokens"],
                      "completion_tokens": metrics["completion_tokens"], "prompt_sha1": digest,
                      "messages": messages, "response": text, "content_from_reasoning": salvaged,
                      "reasoning": reasoning or None}
            if not text.strip():   # only then, so the log does not carry a full dump for every ordinary call
                record["raw_response"] = raw_dump(resp)
            self.io.append(record)
        return text

    def totals(self) -> dict[str, int]:
        ok = [c for c in self.calls if "error" not in c]
        return {"prompt": sum(c.get("prompt_tokens") or 0 for c in ok), "completion": sum(c.get("completion_tokens") or 0 for c in ok),
                "total": sum(c.get("total_tokens") or 0 for c in ok), "errors": len(self.calls) - len(ok),
                "retries": sum(c.get("retries") or 0 for c in ok)}

    def diagnosis(self) -> dict[str, Any]:
        """Why a run may have gone wrong, from the call log alone: output truncated at the token cap, the prompt
        outgrowing the context window, or neither (then the step limit is the remaining suspect)."""
        ok = [c for c in self.calls if "error" not in c]
        bad = [c for c in self.calls if "error" in c]
        truncated = [c["call"] for c in ok if (c.get("finish_reason") or "").lower() in ("length", "max_tokens")]
        return {
            "calls_ok": len(ok), "calls_failed": len(bad),
            "truncated_calls": truncated, "truncated": bool(truncated),
            "empty_responses": sum(1 for c in ok if c.get("empty_response")),
            "content_from_reasoning": sum(1 for c in ok if c.get("content_from_reasoning")),
            "max_prompt_tokens": max((c.get("prompt_tokens") or 0 for c in ok), default=0),
            "max_completion_tokens": max((c.get("completion_tokens") or 0 for c in ok), default=0),
            "max_prompt_chars": max((c.get("prompt_chars") or 0 for c in ok), default=0),
            "context_overflow": any(c.get("error_kind") == "fatal" and "context" in (c.get("detail") or "").lower() for c in bad),
            "error_kinds": {k: sum(1 for c in bad if c.get("error_kind") == k) for k in ("retry", "fatal", "unknown") if any(c.get("error_kind") == k for c in bad)},
            "finish_reasons": {r: sum(1 for c in ok if (c.get("finish_reason") or "none") == r) for r in {(c.get("finish_reason") or "none") for c in ok}},
        }


def failure_suspect(manifest: dict[str, Any], verdict: dict[str, Any] | None) -> str:
    """One label for why this run did not pass, in the order a reader should suspect them.

    `context_overflow` and `output_truncated` are read off the model's own reports; `max_steps` means the agent
    was still working when the step limit cut it off. `wrong_answer` is the interesting case: nothing mechanical
    went wrong, the agent simply got it wrong.
    """
    d = manifest.get("diagnosis", {})
    if manifest.get("status") in ("error", "error_graded"):
        if d.get("context_overflow"):
            return "context_overflow"
        return "run_error"
    if d.get("context_overflow"):
        return "context_overflow"
    if verdict is None:
        return "ungraded"
    if verdict["stock"]["success"]:
        return "pass"
    if d.get("truncated"):
        return "output_truncated"
    if d.get("hit_max_steps"):
        return "max_steps"
    if d.get("empty_responses"):
        return "empty_response"
    return "wrong_answer"


def agent_config(args: argparse.Namespace) -> dict[str, Any]:
    from benchmark_ext.agents import _default_react_prompt_file

    prompt = args.prompt or _default_react_prompt_file()
    return {"scaffold": "appworld_simplified_react_code_agent", "model": args.model, "temperature": args.temperature,
            "max_steps": args.max_steps, "max_output_length": args.max_output_length, "random_seed": 1,
            "prompt_file": os.path.relpath(prompt, PROJECT), "prompt_sha1": hashlib.sha1(open(prompt, "rb").read()).hexdigest()[:12],
            "llm_timeout_s": args.timeout, "llm_retries": args.retries, "api_base": args.api_base,
            # every limit that can end a run has to be in the record, or a truncated reply cannot be told
            # apart from a short one when the results are read back months later
            "max_tokens": args.max_tokens, "retry_budget_s": args.retry_budget, "aws_region": args.aws_region}


def default_agent_id(args: argparse.Namespace) -> str:
    """`react_<vendor>_<model>_t0_s50`. Bedrock ids carry a routing prefix (`bedrock/us.anthropic.claude-opus-5`)
    that says nothing about the model, so drop the transport and the region and keep vendor plus model, which is
    what a reader of the results tree needs."""
    name = args.model.split("/")[-1]
    if args.model.startswith("bedrock/"):
        name = re.sub(r"^(us|eu|apac|global)\.", "", name).split(":")[0]
    slug = name.replace(".", "_").replace("-", "_").replace("/", "_")
    slug = re.sub(r"_+", "_", slug).strip("_")
    temp = "def" if args.temperature is None else f"{args.temperature:g}"   # `tdef` = the provider's own default
    return f"react_{slug}_t{temp}_s{args.max_steps}"


def sample_tasks(tasks: list[str], n: int, seed: int) -> list[str]:
    """A fixed subset of `n`, split evenly across the variants present, so `--sample 100` over
    `compounds,twins` is 50 of each rather than whatever an unstratified draw happens to give. Compounds and
    twins pass at very different rates, so an unbalanced draw would move the headline number on its own.

    Deterministic from `seed`: every model gets the identical set, and growing `n` keeps the smaller set inside
    the larger one. Task order is preserved so the run log reads in task order.
    """
    import random

    if n <= 0 or n >= len(tasks):
        return tasks
    groups: dict[str, list[str]] = {}
    for t in tasks:
        groups.setdefault(store.scenario_of(t)["variant"] or "other", []).append(t)
    picked: set[str] = set()
    for k, (variant, members) in enumerate(sorted(groups.items())):
        share = n // len(groups) + (1 if k < n % len(groups) else 0)   # spread the remainder over the first groups
        shuffled = sorted(members)
        random.Random(f"{seed}:{variant}").shuffle(shuffled)
        picked.update(shuffled[:share])
    return [t for t in tasks if t in picked]


# ---- one run, in this process ------------------------------------------------------------------------------------

def run_one(args: argparse.Namespace) -> dict[str, Any]:
    from appworld.common.path_store import path_store

    keep_aws_clock_real()   # before AppWorld freezes the clock, or bedrock signatures arrive expired
    task_id, agent_id, attempt = args.one, args.agent_id, args.attempt
    exp = f"{agent_id}__a{attempt}"
    scratch = os.path.join(SCRATCH, agent_id, f"{task_id}-{os.getpid()}")
    os.makedirs(scratch, exist_ok=True)
    root = compose_root(scratch)
    path_store.update_root(root)
    dest = store.run_dir(agent_id, task_id, attempt)
    if os.path.exists(dest):  # a half-written attempt: keep it aside, it is not done
        shutil.move(dest, f"{dest}.failed.{time.strftime('%Y%m%dT%H%M%S')}")
    config = agent_config(args)
    manifest: dict[str, Any] = {"agent_id": agent_id, "task_id": task_id, "attempt": attempt, "experiment": exp, "scenario": store.scenario_of(task_id),
                                "model": args.model, "agent": config, "started_at": store.now(), "status": "running", "commits": store.commits(),
                                "python": sys.version.split()[0], "seed": 1}
    llm = LoggedLLM(args.model, temperature=args.temperature, timeout=args.timeout, retries=config["llm_retries"], api_base=args.api_base,
                    aws_region=args.aws_region, retry_budget_s=args.retry_budget, max_tokens=args.max_tokens)
    real_time, real_now = _real_clock()   # AppWorld freezes the clock for the task; the run is timed on the real one
    t0 = real_time()
    verdict: dict[str, Any] | None = None
    try:
        from appworld.evaluator import evaluate_task

        from benchmark_ext.agents import appworld_agent
        from benchmark_ext.runner import run_extended_task

        agent = appworld_agent(llm=llm, max_steps=args.max_steps, max_output_length=args.max_output_length, prompt_file_path=args.prompt)
        extended = run_extended_task(task_id, agent, experiment_name=exp)
        stock = evaluate_task(task_id, experiment_name=exp, save_report=False)
        verdict = {"graded_at": store.now(), "grader_commit": manifest["commits"]["appworld_extend"],
                   "stock": store.tracker_dict(stock), "extended": store.tracker_dict(extended)}
        manifest["status"] = "ok"
    except Exception as exc:
        manifest["status"] = "error"
        manifest["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        manifest["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
        try:  # keep whatever state the world reached, so the failed attempt can still be inspected
            from appworld.environment import AppWorld
            AppWorld.close_all()
        except Exception:
            pass
        # A limit the agent cannot get past (context window, request the model rejects) is a real result, not
        # an infrastructure fault. Grade the state it did reach so the run counts, instead of leaving no
        # verdict and being retried identically forever. Other errors keep the old behaviour and are retried.
        if is_model_limit(exc):
            try:
                from appworld.evaluator import evaluate_task

                from benchmark_ext.evaluate import evaluate_task_extended
                from benchmark_ext.task_meta import load_task_meta
                extended = evaluate_task_extended(task_id, experiment_name=exp, task_meta=load_task_meta(task_id))
                stock = evaluate_task(task_id, experiment_name=exp, save_report=False)
                verdict = {"graded_at": store.now(), "grader_commit": manifest["commits"]["appworld_extend"],
                           "stock": store.tracker_dict(stock), "extended": store.tracker_dict(extended)}
                manifest["status"] = "error_graded"
            except Exception as gexc:
                manifest["grade_after_error"] = f"{type(gexc).__name__}: {str(gexc)[:200]}"
    manifest["finished_at"] = real_now()
    manifest["duration_s"] = round(real_time() - t0, 1)
    manifest["llm_calls"] = len(llm.calls)
    manifest["steps"] = len([c for c in llm.calls if "error" not in c])
    manifest["tokens"] = llm.totals()
    manifest["diagnosis"] = llm.diagnosis()
    manifest["diagnosis"]["hit_max_steps"] = manifest["steps"] >= args.max_steps
    manifest["failure_suspect"] = failure_suspect(manifest, verdict)
    out = os.path.join(root, "experiments", "outputs", exp, "tasks", task_id)
    target = dest if manifest["status"] in ("ok", "error_graded") else f"{dest}.failed.{time.strftime('%Y%m%dT%H%M%S')}"
    os.makedirs(target, exist_ok=True)
    if os.path.isdir(out):
        shutil.move(out, os.path.join(target, "appworld"))
        for name in ("code.txt", "data.txt"):
            p = os.path.join(target, "appworld", "version", name)
            if os.path.isfile(p):
                manifest.setdefault("versions", {})[name.split(".")[0]] = open(p).read().strip()
    with open(os.path.join(target, "llm_calls.jsonl"), "w") as f:
        for c in llm.calls:
            f.write(json.dumps(c, sort_keys=True) + "\n")
    with open(os.path.join(target, "llm_io.jsonl"), "w") as f:   # the prompts and replies themselves
        for c in llm.io:
            f.write(json.dumps(c, sort_keys=True) + "\n")
    store.write_json(os.path.join(target, "manifest.json"), manifest)
    if verdict is not None:
        store.write_json(os.path.join(target, "verdict.json"), verdict)
    shutil.rmtree(scratch, ignore_errors=True)
    row = {"task_id": task_id, "status": manifest["status"], "duration_s": manifest["duration_s"], "steps": manifest["steps"],
           "tokens": manifest["tokens"]["total"], "error": manifest.get("error"),
           "suspect": manifest["failure_suspect"], "retries": manifest["tokens"]["retries"],
           "max_prompt_tokens": manifest["diagnosis"]["max_prompt_tokens"]}
    if verdict is not None:
        row["stock_success"] = verdict["stock"]["success"]
        row["modes_fired"] = verdict["extended"]["modes_fired"]
    return row


# ---- regrade one stored run, in this process -----------------------------------------------------------------------

def regrade_one(args: argparse.Namespace) -> dict[str, Any]:
    from appworld.common.path_store import path_store

    task_id, agent_id, attempt = args.regrade_one, args.agent_id, args.attempt
    d = store.run_dir(agent_id, task_id, attempt)
    manifest = store.read_json(os.path.join(d, "manifest.json"))
    exp = manifest["experiment"]
    scratch = os.path.join(SCRATCH, agent_id, f"regrade-{task_id}-{os.getpid()}")
    os.makedirs(scratch, exist_ok=True)
    root = compose_root(scratch)
    tasks_out = os.path.join(root, "experiments", "outputs", exp, "tasks")
    os.makedirs(tasks_out, exist_ok=True)
    os.symlink(os.path.abspath(os.path.join(d, "appworld")), os.path.join(tasks_out, task_id))
    path_store.update_root(root)
    from appworld.evaluator import evaluate_task

    from benchmark_ext.evaluate import evaluate_task_extended
    from benchmark_ext.task_meta import load_task_meta

    extended = evaluate_task_extended(task_id, experiment_name=exp, task_meta=load_task_meta(task_id))
    stock = evaluate_task(task_id, experiment_name=exp, save_report=False)
    verdict = {"graded_at": store.now(), "grader_commit": store.commits()["appworld_extend"],
               "stock": store.tracker_dict(stock), "extended": store.tracker_dict(extended)}
    old_path = os.path.join(d, "verdict.json")
    old = store.read_json(old_path) if os.path.isfile(old_path) else None
    if old is not None and not os.path.isfile(os.path.join(d, "verdict.prev.json")):   # the first previous verdict is kept
        shutil.copy(old_path, os.path.join(d, "verdict.prev.json"))
    store.write_json(old_path, verdict)
    shutil.rmtree(scratch, ignore_errors=True)
    changed = old is not None and (old["stock"]["success"] != verdict["stock"]["success"] or old["extended"].get("modes_fired") != verdict["extended"]["modes_fired"])
    return {"task_id": task_id, "status": "regraded", "changed": bool(changed), "stock_success": verdict["stock"]["success"], "modes_fired": verdict["extended"]["modes_fired"]}


# ---- the scheduler ---------------------------------------------------------------------------------------------------

def _child(argv: list[str], timeout: float) -> dict[str, Any]:
    try:
        # PYTHONHASHSEED pinned: AppWorld's changed-record sets iterate in string-hash order, so a stock requirement
        # that keys records by a field the agent duplicated (two requests to one receiver, a676f2ac in pass 5)
        # otherwise flips between regrades. The seed fixes the order; the verdict is then reproducible.
        proc = subprocess.run([sys.executable, "-m", "benchmark_ext.run", *argv], cwd=PROJECT, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "PYTHONHASHSEED": "0"})
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"no result within {timeout:.0f}s"}
    line = next((l for l in reversed(proc.stdout.splitlines()) if l.startswith("{")), None)
    if proc.returncode != 0 or not line:
        tail = (proc.stderr.strip().splitlines() or ["no output"])[-1][:300]
        return {"status": "crashed", "error": tail}
    return json.loads(line)


def schedule(args: argparse.Namespace) -> None:
    tasks = store.select_tasks(args.tasks)
    if args.scenario:
        tasks = [t for t in tasks if store.scenario_of(t)["anchor"] in set(args.scenario.split(","))]
    if args.sample:
        tasks = sample_tasks(tasks, args.sample, args.sample_seed)
    regrade = bool(args.regrade)
    pending = [t for t in tasks if (store.is_done(args.agent_id, t, args.attempt) if regrade else not store.is_done(args.agent_id, t, args.attempt))]
    already_done = len(tasks) - len(pending)   # counted before --limit, or the limit reads as done work
    if args.limit:
        pending = pending[: args.limit]
    verb = "regrade" if regrade else "run"
    print(f"{verb}: {len(pending)} of {len(tasks)} selected tasks for agent {args.agent_id!r}, attempt {args.attempt}"
          + ("" if regrade else f" ({already_done} already done)"))
    if args.dry_run or not pending:
        for t in pending:
            print("  ", t)
        return
    if not regrade:
        store.register_agent(args.agent_id, agent_config(args))
        load_provider_key(args.model)
    common = ["--agent-id", args.agent_id, "--attempt", str(args.attempt), "--model", args.model,
              "--max-steps", str(args.max_steps), "--timeout", str(args.timeout), "--retries", str(args.retries),
              "--retry-budget", str(args.retry_budget), "--aws-region", args.aws_region]
    if args.temperature is not None:   # left off entirely means the model's own default
        common += ["--temperature", str(args.temperature)]
    if args.max_tokens is not None:
        common += ["--max-tokens", str(args.max_tokens)]
    if args.max_output_length is not None:
        common += ["--max-output-length", str(args.max_output_length)]
    if args.api_base:
        common += ["--api-base", args.api_base]
    if args.prompt:
        common += ["--prompt", args.prompt]
    store.log_line(args.agent_id, f"{verb} start: {len(pending)} tasks, workers={args.workers}")
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_child, (["--regrade-one", t] if regrade else ["--one", t]) + common, args.run_timeout): t for t in pending}
        for fut in as_completed(futures):
            t = futures[fut]
            row = fut.result()
            done += 1
            line = f"[{done}/{len(pending)}] {t}: {row.get('status')} stock={row.get('stock_success')} suspect={row.get('suspect')} modes={row.get('modes_fired')} steps={row.get('steps')} tokens={row.get('tokens')} retries={row.get('retries')} {row.get('duration_s', '')}s {row.get('error') or ''}"
            print(line, flush=True)
            store.log_line(args.agent_id, line)
    # Both of these walk the WHOLE results tree and read every manifest and verdict, so each costs a full scan
    # (two, since summary() rebuilds the rows itself). At ~250k runs on shared Lustre that dwarfs the runs this
    # invocation actually did, and a short retry round pays it for a handful of tasks. The index is derived, so
    # `--no-index` skips it; regenerate any time with `--index`.
    if not args.no_index:
        store.rebuild_index()
        print(store.summary())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tasks", default="compounds,twins", help="compounds, twins, ablations, hard, all, a glob, or task ids (comma list)")
    p.add_argument("--scenario", default=None, help="keep only these anchors (comma list)")
    p.add_argument("--agent-id", default=None)
    p.add_argument("--attempt", type=int, default=1)
    p.add_argument("--model", default=DEFAULT_MODEL, help="a litellm model id: gemini/..., openai/..., anthropic/..., openrouter/<vendor>/..., hosted_vllm/... ")
    p.add_argument("--api-base", default=None, help="an OpenAI-compatible endpoint, for a model you serve yourself (recorded, not part of the agent id)")
    p.add_argument("--temperature", type=float, default=None,
                   help="omitted by default, so each model uses its own: reasoning models reject a pinned value "
                        "(claude-opus-5, claude-sonnet-5 and the gpt-5.6 ids all refuse temperature=0). "
                        "Pass --temperature 0 for the old fixed setting; the agent id records which was used "
                        "(t0 vs tdef), so the two never share a results directory")
    p.add_argument("--max-steps", type=int, default=50, help="AppWorld's leaderboard setting for this agent; passes 1 to 5 ran at 40, the code default")
    p.add_argument("--max-output-length", type=int, default=None)
    p.add_argument("--prompt", default=None, help="prompt file (default: AppWorld's simplified ReAct prompt)")
    p.add_argument("--timeout", type=float, default=180.0, help="per model call, seconds")
    p.add_argument("--retries", type=int, default=5, help="per model call, for an error we cannot classify; a known "
                                                          "service fault (rate limit, throttle, 5xx, timeout) retries without limit")
    p.add_argument("--retry-budget", type=float, default=1800.0, help="stop retrying one model call after this long, seconds")
    p.add_argument("--max-tokens", type=int, default=None, help="cap on each model reply; reasoning models need room")
    p.add_argument("--aws-region", default=os.environ.get("AWS_REGION") or "us-west-2", help="region for bedrock/... models")
    p.add_argument("--sample", type=int, default=0, help="smoke test: run this many tasks, sampled evenly across the "
                                                         "selection with a fixed seed, so every model sees the same set")
    p.add_argument("--sample-seed", type=int, default=1234)
    p.add_argument("--run-timeout", type=float, default=2400.0, help="per run, seconds")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--pending", action="store_true",
                   help="print how many of the selected tasks still have no verdict for this agent and "
                        "attempt, then exit; lets a caller loop until a pass is genuinely complete")
    p.add_argument("--no-index", action="store_true",
                   help="skip the end-of-run index rebuild and summary; both scan the whole results tree")
    p.add_argument("--regrade", action="store_true")
    p.add_argument("--index", action="store_true")
    p.add_argument("--one", default=None, help=argparse.SUPPRESS)
    p.add_argument("--regrade-one", default=None, help=argparse.SUPPRESS)
    args = p.parse_args()
    args.agent_id = args.agent_id or default_agent_id(args)
    if args.index:
        print(store.rebuild_index()); print(store.summary()); return
    if args.pending:
        sel = store.select_tasks(args.tasks)
        if args.scenario:
            sel = [t for t in sel if store.scenario_of(t)["anchor"] in set(args.scenario.split(","))]
        if args.sample:
            sel = sample_tasks(sel, args.sample, args.sample_seed)
        print(sum(1 for t in sel if not store.is_done(args.agent_id, t, args.attempt)))
        return
    if args.one:
        load_provider_key(args.model)
        print(json.dumps(run_one(args), default=str)); return
    if args.regrade_one:
        print(json.dumps(regrade_one(args), default=str)); return
    schedule(args)


if __name__ == "__main__":
    main()
