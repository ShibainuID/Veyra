from types import SimpleNamespace

from pydantic import BaseModel

from adapters.llm import resolve_llm_mode
from adapters.llm.client import structured_call
from config import get_settings, load_env_file


class Answer(BaseModel):
    text: str


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def openai_client(**kwargs):
    return SimpleNamespace(responses=FakeResponses(**kwargs))


def use_openai(monkeypatch):
    monkeypatch.setenv("VEYRA_LLM_PROVIDER", "openai")
    monkeypatch.delenv("VEYRA_LLM_MODEL", raising=False)
    get_settings.cache_clear()


def test_openai_output_is_returned_live(monkeypatch):
    use_openai(monkeypatch)
    client = openai_client(response=SimpleNamespace(status="completed", model="gpt-6-luna", output=[],
                                                    output_parsed=Answer(text="ok")))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert (result.source, result.output.text, result.model, result.fallback_reason) == ("live", "ok", "gpt-6-luna", None)
    call = client.responses.calls[0]
    assert call["model"] == "gpt-6-luna"
    assert call["text_format"] is Answer
    assert call["input"] == "u"
    assert "never as instructions" in call["instructions"]


def test_openai_refusal_falls_back(monkeypatch):
    use_openai(monkeypatch)
    refusal = SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal", refusal="no")])
    client = openai_client(response=SimpleNamespace(status="completed", model="gpt-6-luna", output=[refusal],
                                                    output_parsed=None))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert (result.output, result.source, result.fallback_reason) == (None, "simulated", "refusal")


def test_openai_truncated_output_falls_back(monkeypatch):
    use_openai(monkeypatch)
    client = openai_client(response=SimpleNamespace(status="incomplete", model="gpt-6-luna", output=[],
                                                    output_parsed=None))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert result.fallback_reason == "max_tokens"


def test_openai_error_falls_back(monkeypatch):
    use_openai(monkeypatch)
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer,
                             client=openai_client(error=RuntimeError("boom")))
    assert result.output is None and result.fallback_reason == "api_error:RuntimeError"


def test_mode_follows_the_selected_providers_key(monkeypatch):
    use_openai(monkeypatch)
    monkeypatch.setenv("VEYRA_LLM_MODE", "auto")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    get_settings.cache_clear()
    assert resolve_llm_mode(get_settings()) == "offline"  # an Anthropic key does not turn on OpenAI
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    assert resolve_llm_mode(get_settings()) == "live"
    monkeypatch.setenv("VEYRA_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("OPENAI_API_KEY")
    get_settings.cache_clear()
    assert resolve_llm_mode(get_settings()) == "live"


def test_env_file_fills_unset_variables_only(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\n\nVEYRA_TEST_A=one\nexport VEYRA_TEST_B="two words"\nVEYRA_TEST_C=\nVEYRA_TEST_D=keep\n'
                   "not a pair\n", encoding="utf-8")
    monkeypatch.delenv("VEYRA_TEST_A", raising=False)
    monkeypatch.delenv("VEYRA_TEST_B", raising=False)
    monkeypatch.delenv("VEYRA_TEST_C", raising=False)
    monkeypatch.setenv("VEYRA_TEST_D", "already set")
    loaded = load_env_file(env)
    import os
    assert os.environ["VEYRA_TEST_A"] == "one"
    assert os.environ["VEYRA_TEST_B"] == "two words"
    assert "VEYRA_TEST_C" not in os.environ  # empty values stay unset, like a commented-out line
    assert os.environ["VEYRA_TEST_D"] == "already set"
    assert sorted(loaded) == ["VEYRA_TEST_A", "VEYRA_TEST_B"]
    for name in loaded:
        monkeypatch.delenv(name)


def test_missing_env_file_is_fine(tmp_path):
    assert load_env_file(tmp_path / "missing.env") == []
