"""Provider-agnostic agent adapters — run ANY agent against the benchmark.

Three ways to plug an agent into `run_extended_task(task_id, agent, ...)`:

1) A full custom agent — any callable `agent(world) -> list[{"interaction","text"}]` that drives
   `world.execute(...)` / `world.apis.*` however it likes (the golds in `gold.py` are examples).

2) An LLM via a thin built-in ReAct loop — `react_agent(llm)` (zero appworld-agents deps).
   - Recommended: `litellm_llm("gemini/gemini-2.5-flash")` — the SAME backend AppWorld's own scaffold
     uses; route by model-name prefix, no base URLs (`pip install litellm`).
   - Zero-dependency alternative: `openai_chat_llm(model, base_url=…)` — raw `requests` to any
     OpenAI-compatible endpoint (needs a base_url; no SDK).
   - Anything else: `llm` is just any `Callable[[list[Message]], str]` — a ~5-line adapter.

3) AppWorld's OWN reference agent — `appworld_agent(llm=…)` (maximal reuse; recommended for the paper).
   Runs the real, paper-validated `SimplifiedReActCodeAgent` (its tuned prompt, ReAct loop, code
   extraction, and reasoning pass-through) on OUR overlay world, so the failure profile reflects the
   MODEL, not a custom scaffold — and results are comparable to AppWorld's leaderboard. Same
   provider-agnostic backend as (2): `appworld_agent(llm=litellm_llm("gemini/…"))` or
   `appworld_agent(model="gemini/gemini-2.5-flash")`. Requires `pip install -e appworld/experiments`.

       tracker = run_extended_task("c83a7951_compound", react_agent(litellm_llm("gemini/gemini-2.5-flash")))
       tracker = run_extended_task("c83a7951_compound", appworld_agent(model="gemini/gemini-2.5-flash"))
       profile = tracker.category_success()   # per-failure-mode pass/fail

Note: all three run through OUR `run_extended_task` (overlay + `evaluate_extended` = the 11-mode
profile). AppWorld's own `Agent.solve_task` builds its own world and grades with the STOCK evaluator,
so it does not produce that profile — the extended grading is necessarily this layer. `appworld_agent`
reuses their *agent* (the loop) while we keep our world construction + extended grading.
"""
from __future__ import annotations

import re
from typing import Any, Callable

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}
LanguageModel = Callable[[list["Message"]], str]

DEFAULT_SYSTEM_PROMPT = (
    "You are an autonomous agent that completes tasks in a simulated digital world by writing "
    "Python code executed in a stateful REPL. Rules:\n"
    "- Read the task: print(apis.supervisor.show_active_task()).\n"
    "- Your email: apis.supervisor.show_profile()['email']. "
    "Passwords: apis.supervisor.show_account_passwords().\n"
    "- Discover APIs: apis.api_docs.show_api_descriptions(app_name=...) and "
    "apis.api_docs.show_api_doc(app_name=..., api_name=...).\n"
    "- Log in per app: token = apis.<app>.login(username=<email>, password=<password>)['access_token']; "
    "then call apis.<app>.<endpoint>(access_token=token, ...).\n"
    "- Reason briefly, then output EXACTLY ONE ```python ... ``` code block per turn. "
    "print(...) anything you need to observe.\n"
    "- Do not use input(); act autonomously.\n"
    "- When finished, call apis.supervisor.complete_task(answer=<answer or None>, status='success')."
)


def extract_code(text: str) -> str:
    """First ```python fenced block, then any ``` fenced block, else empty (no action)."""
    for pattern in (r"```python\s*\n(.*?)```", r"```\s*\n(.*?)```"):
        match = re.search(pattern, text or "", re.DOTALL)
        if match:
            return match.group(1).strip()
    return ""


def messages_to_prompt(messages: list[Message]) -> str:
    """Flatten a chat message list into one prompt string (for models that take a string)."""
    return "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)


def litellm_llm(model: str, **kwargs: Any) -> LanguageModel:
    """Provider-agnostic `llm` via litellm — the backend AppWorld's own scaffold uses. Route by model
    NAME PREFIX, no base URLs and no adapter; keys come from each provider's usual env var. Requires
    `pip install litellm` (an appworld experiments dependency).

        react_agent(litellm_llm("gemini/gemini-2.5-flash"))    # or "openrouter/…", "deepseek/…", "gpt-4o", …
    """

    def llm(messages: list[Message]) -> str:
        import litellm

        response = litellm.completion(model=model, messages=messages, **kwargs)
        return response.choices[0].message.content

    return llm


def openai_chat_llm(
    model: str | None = None,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    extra_headers: dict | None = None,
) -> LanguageModel:
    """One `llm` for ANY OpenAI-compatible `/chat/completions` endpoint — no SDK, no adapter, and NO
    provider special-cased. OpenRouter, OpenAI, native Gemini (compat), DeepSeek, Kimi/Moonshot, Groq,
    Together, a local vLLM/Ollama server, ... all work the same; only `model`/`base_url`/`api_key`
    differ, and each comes from the argument OR the environment:

        export LLM_BASE_URL=...   LLM_API_KEY=...   LLM_MODEL=...
        tracker = run_extended_task(task, react_agent(openai_chat_llm()))   # identical for every provider

    `base_url` <- arg or $LLM_BASE_URL (your provider's endpoint, e.g. https://openrouter.ai/api/v1;
                 native Gemini: https://generativelanguage.googleapis.com/v1beta/openai).
    `model`    <- arg or $LLM_MODEL.
    `api_key`  <- arg or $LLM_API_KEY (then $OPENROUTER_API_KEY/$OPENAI_API_KEY/$GEMINI_API_KEY/$GOOGLE_API_KEY).
    """
    import os

    import requests

    model = model or os.environ.get("LLM_MODEL")
    base_url = base_url or os.environ.get("LLM_BASE_URL")
    api_key = (
        api_key
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not model:
        raise RuntimeError("Set model=... or $LLM_MODEL")
    if not base_url:
        raise RuntimeError("Set base_url=... or $LLM_BASE_URL (your provider's OpenAI-compatible "
                           "endpoint, e.g. https://openrouter.ai/api/v1)")

    def llm(messages: list[Message]) -> str:
        if not api_key:
            raise RuntimeError("Set api_key=... or $LLM_API_KEY (or a provider key env var)")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    return llm


def _is_done(world: Any, code: str) -> bool:
    if "complete_task" in code:
        return True
    try:
        return bool(world.task_completed())
    except Exception:
        return False


def react_agent(
    llm: LanguageModel,
    *,
    max_steps: int = 25,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    verbose: bool = False,
) -> Callable[[Any], list[Message]]:
    """Wrap a provider-agnostic `llm` into an `agent(world)` the runner can execute."""

    def agent(world: Any) -> list[Message]:
        task = world.execute("print(apis.supervisor.show_active_task())")
        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task:\n{task}\n\nWrite Python for the next step."},
        ]
        reasoning: list[Message] = []
        for step in range(max_steps):
            assistant = llm(messages) or ""
            messages.append({"role": "assistant", "content": assistant})
            reasoning.append({"interaction": step + 1, "text": assistant})  # CoT -> mode 11
            code = extract_code(assistant)
            if verbose:
                print(f"[step {step + 1}]\n{code}\n")
            if not code:
                break
            observation = world.execute(code)
            messages.append({"role": "user", "content": f"Output:\n{observation}"})
            if _is_done(world, code):
                break
        return reasoning

    return agent


# ---- Option 3: AppWorld's OWN reference agent, run on our overlay world ----------------------

def _default_react_prompt_file() -> str:
    """AppWorld's packaged react_code_agent/instructions.txt (ships with appworld-agents)."""
    import os

    import appworld_agents  # maps to appworld/experiments; prompts live alongside the code

    path = os.path.join(
        os.path.dirname(appworld_agents.__file__), "prompts", "react_code_agent", "instructions.txt"
    )
    if not os.path.isfile(path):
        raise RuntimeError(f"AppWorld react prompt not found at {path}")
    return path


class _LMAdapter:
    """Adapt our provider-agnostic `llm(messages) -> str` to AppWorld's `LanguageModel.generate()`
    dict contract. Lets AppWorld's real agent run on any provider via our clean LLM layer — and
    sidesteps AppWorld's LanguageModel eagerly constructing an `OpenAI()` client (which would force
    OPENAI_API_KEY even when routing elsewhere)."""

    def __init__(self, llm: LanguageModel):
        self._llm = llm

    def generate(self, messages: list[dict], tools: Any = None,
                 cache_control_at: Any = None, **kwargs: Any) -> dict:
        from appworld_agents.code.common.usage_tracker import Usage

        clean = [{"role": m["role"], "content": m.get("content") or ""} for m in messages]
        return {"role": "assistant", "content": self._llm(clean) or "",
                "standardized_usage": Usage()}

    def log_calls_to(self, file_path: str | None = None, world: Any = None) -> None:
        pass


# CostPerToken requires all four fields; zero them (we don't track cost for a benchmark run).
_ZERO_COST = {"input_cache_hit": 0.0, "input_cache_miss": 0.0, "input_cache_write": 0.0, "output": 0.0}


def appworld_agent(
    llm: LanguageModel | None = None,
    *,
    model: str | None = None,
    model_config: dict | None = None,
    prompt_file_path: str | None = None,
    max_steps: int = 40,
    appworld_config: dict | None = None,
    verbose: bool = False,
    max_output_length: int | None = None,
) -> Callable[[Any], list[Message]]:
    """Run AppWorld's OWN `SimplifiedReActCodeAgent` (loop + tuned prompt + code extraction) on our
    overlay world, returning per-step reasoning (incl. hidden `reasoning_content` -> mode 11).

    Backend (pick one):
      * `llm=<callable>`  — any `Callable[[messages], str]` (e.g. `litellm_llm("gemini/…")`,
        `openai_chat_llm(...)`, or a stub). Friction-free; no extra env quirks.  [default]
      * `model=<name>`    — shorthand for `llm=litellm_llm(model)`.
      * `model_config=<dict>` — AppWorld's EXACT `LanguageModel` (caching/cost/retry + hidden
        reasoning_content for reasoning models). Full fidelity, but AppWorld's LanguageModel builds
        an `OpenAI()` client eagerly, so OPENAI_API_KEY must be set (any value) even for litellm
        routing. See `appworld/experiments/configs/simplified_react_code_agent/*` for the shape.

    The returned `agent(world)` reuses AppWorld's agent across runs (its `initialize(world)` resets
    state per task). `agent.simplified_agent` exposes the underlying real agent for introspection.
    """
    import appworld_agents.code.simplified.agent as agent_mod
    from appworld_agents.code.simplified.agent import ExecutionIO
    from appworld_agents.code.simplified.react_code_agent import SimplifiedReActCodeAgent

    build_kwargs = dict(
        prompt_file_path=prompt_file_path or _default_react_prompt_file(),
        appworld_config=appworld_config or {"random_seed": 1},
        logger_config={"verbose": verbose, "color": False},
        usage_tracker_config={},
        max_steps=max_steps,
        log_lm_calls=False,
        # AppWorld's OWN context management, opt-in and OFF by default (109 of its shipped configs set null,
        # 23 set 20000). When set, `trimmed_messages` blanks old OBSERVATIONS to "[NOT SHOWN FOR BREVITY]"
        # oldest-first, keeping the last 5 blocks; the task statement lives in the prompt and is never blanked.
        max_output_length=max_output_length,
    )

    if model_config is not None:
        # AppWorld's exact LanguageModel (canonical transport).
        merged = {"cost_per_token": _ZERO_COST, "use_cache": False, **model_config}
        try:
            sr = SimplifiedReActCodeAgent(model_config=merged, **build_kwargs)
        except Exception as exc:  # OpenAI() eager-construct needs a key even for litellm routing
            if "api_key" in str(exc).lower():
                raise RuntimeError(
                    "AppWorld's LanguageModel constructs an OpenAI() client eagerly, so "
                    "OPENAI_API_KEY must be set (any value) even when routing to another provider "
                    "via litellm. Set it, or use the llm=/model= backend instead."
                ) from exc
            raise
    else:
        backend = llm if llm is not None else (litellm_llm(model) if model else None)
        if backend is None:
            raise RuntimeError("Pass llm=<callable>, model=<litellm name>, or model_config=<dict>.")
        adapter = _LMAdapter(backend)
        original = agent_mod.LanguageModel
        agent_mod.LanguageModel = lambda **_: adapter  # inject; avoid the eager OpenAI() construct
        try:
            sr = SimplifiedReActCodeAgent(model_config={"name": model or "adapter"}, **build_kwargs)
        finally:
            agent_mod.LanguageModel = original

    def agent(world: Any) -> list[Message]:
        sr.initialize(world)  # point AppWorld's own agent at OUR overlay-installed world
        execution_outputs: list = []
        reasoning: list[Message] = []
        for step in range(sr.max_steps):
            sr.step_number += 1
            inputs, usage, status = sr.next_execution_inputs_usage_and_status(execution_outputs)
            if status.failed:
                break
            emitted = sr.messages[-1]  # the agent's output just appended (content + reasoning_content)
            text = (emitted.get("content") or "").strip()
            thought = (emitted.get("reasoning_content") or "").strip()
            reasoning.append({"interaction": step + 1,
                              "text": f"{thought}\n\n{text}".strip() if thought else text})
            code = inputs[0].content if inputs else ""
            if verbose:
                print(f"[step {step + 1}]\n{code}\n")
            try:
                observation = world.execute(code)
            except Exception as exc:  # an app-side crash (e.g. a response the server cannot encode) is the agent's to see, not the run's to die of
                observation = f"Exception: {type(exc).__name__}: {str(exc)[:1000]}"
            execution_outputs = [ExecutionIO(content=observation, metadata=inputs[0].metadata)]
            sr.usage_tracker.add(world.task_id, usage)
            if world.task_completed() or sr.usage_tracker.exceeded(world.task_id):
                break
        return reasoning

    agent.simplified_agent = sr  # expose the real AppWorld agent (introspection / tests)
    return agent
