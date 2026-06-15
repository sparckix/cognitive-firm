from __future__ import annotations

import pytest

from cognitive_firm.common import llm_runtime
from cognitive_firm.common.llm_runtime import (
    LLMRuntime,
    openai_compatible_effective_model_id,
    pick_default_model_id_for_scripts,
    resolve_director_model_id,
    resolve_model_id,
)


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_COMPATIBLE_MODEL",
        "LOCAL_LLM_MODEL",
        "OSS_MODEL",
        "LLM_DISPATCH_PREF",
    ):
        monkeypatch.delenv(key, raising=False)
    for fn_name in ("_read_principal_model_economy", "_read_principal_preferred_provider"):
        fn = getattr(llm_runtime, fn_name)
        if hasattr(fn, "_cached"):
            delattr(fn, "_cached")


def test_deepseek_model_aliases_resolve() -> None:
    assert resolve_model_id("deepseek") == "deepseek-chat"
    assert resolve_model_id("deepseek-reasoner") == "deepseek-reasoner"
    assert resolve_director_model_id("deepseek") == "deepseek-reasoner"


def test_openai_compatible_aliases_resolve_to_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)

    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "qwen2.5-coder")

    assert resolve_model_id("oss") == "openai-compatible"
    assert openai_compatible_effective_model_id("openai-compatible") == "qwen2.5-coder"
    assert openai_compatible_effective_model_id("local:llama3.3") == "llama3.3"


def test_openai_compatible_requires_model_when_no_inline_or_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)

    with pytest.raises(RuntimeError, match="OPENAI_COMPATIBLE_MODEL"):
        openai_compatible_effective_model_id("openai-compatible")


def test_provider_configuration_recognizes_deepseek_and_openai_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)
    runtime = LLMRuntime()

    assert runtime.model_is_configured("deepseek-chat") is False
    assert runtime.model_is_configured("openai-compatible:llama3.3") is False

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:11434/v1")

    assert runtime.model_is_configured("deepseek-chat") is True
    assert runtime.model_is_configured("openai-compatible:llama3.3") is True


def test_default_model_picker_honors_deepseek_and_local_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)

    monkeypatch.setenv("LLM_DISPATCH_PREF", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    assert pick_default_model_id_for_scripts() == "deepseek-chat"

    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_DISPATCH_PREF", "local")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:11434/v1")
    assert pick_default_model_id_for_scripts() == "openai-compatible"
