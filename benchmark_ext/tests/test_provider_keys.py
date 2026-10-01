"""The runner loads the key variable of the model's provider by name, and none for a self-served model."""
from benchmark_ext.run import provider_key_var


def test_provider_prefix_maps_to_the_variable_litellm_reads():
    assert provider_key_var("gemini/gemini-3.1-pro-preview") == "GEMINI_API_KEY"
    assert provider_key_var("anthropic/claude-x") == "ANTHROPIC_API_KEY"
    assert provider_key_var("openrouter/google/gemma") == "OPENROUTER_API_KEY"
    assert provider_key_var("gpt-4o") == "OPENAI_API_KEY"          # a bare name is OpenAI's


def test_a_locally_served_model_needs_no_key():
    assert provider_key_var("hosted_vllm/meta-llama/Llama-3-70B") is None
    assert provider_key_var("ollama/llama3") is None
    assert provider_key_var("bedrock/us.anthropic.claude-opus-5") is None   # signs with AWS credentials


def test_an_unnamed_provider_falls_back_to_litellms_own_convention():
    assert provider_key_var("fireworks_ai/x") == "FIREWORKS_AI_API_KEY"
    assert provider_key_var("cerebras/x") == "CEREBRAS_API_KEY"


def test_a_rate_limit_is_retried_however_the_provider_wraps_it():
    """The real gemini-3.8-flash failure: quota exhaustion arrived as a BadRequestError carrying a 429 body.
    FATAL's "badrequest" matched the class name first and 313 runs were abandoned instead of retried."""
    from benchmark_ext.run import classify_llm_error

    class BadRequestError(Exception):
        pass

    gemini_quota = BadRequestError(
        'litellm.BadRequestError: GeminiException BadRequestError - {"error": {"code": 429, '
        '"message": "You exceeded your current quota, please check your plan and billing details."}}')
    assert classify_llm_error(gemini_quota) == "retry"
    assert classify_llm_error(Exception("RateLimitError: too many requests")) == "retry"
    assert classify_llm_error(Exception("ThrottlingException: slow down")) == "retry"
    # a genuinely malformed request must still be fatal: no rate-limit signal anywhere in it
    assert classify_llm_error(BadRequestError("litellm.BadRequestError: model does not support tools")) == "fatal"
    assert classify_llm_error(Exception("AuthenticationError: invalid api key")) == "fatal"
