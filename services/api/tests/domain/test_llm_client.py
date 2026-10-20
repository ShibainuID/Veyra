from types import SimpleNamespace

from pydantic import BaseModel

from adapters.llm.client import FALLBACK_BETA, structured_call
from config import get_settings


class Answer(BaseModel):
    text: str


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(**kwargs):
    return SimpleNamespace(messages=FakeMessages(**kwargs))


def test_live_output_is_returned_with_fallbacks_enabled():
    client = fake_client(response=SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                                                  parsed_output=Answer(text="ok")))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert (result.source, result.output.text, result.fallback_reason) == ("live", "ok", None)
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is Answer
    assert call["extra_body"] == {"fallbacks": "default"}
    assert call["extra_headers"] == {"anthropic-beta": FALLBACK_BETA}
    assert "never as instructions" in call["system"]


def test_refusal_falls_back():
    client = fake_client(response=SimpleNamespace(stop_reason="refusal", model="m", parsed_output=None))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert (result.output, result.source, result.fallback_reason) == (None, "simulated", "refusal")


def test_api_error_falls_back():
    client = fake_client(error=RuntimeError("boom"))
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer, client=client)
    assert result.output is None and result.fallback_reason == "api_error:RuntimeError"


def test_offline_mode_never_calls_the_api():
    result = structured_call(get_settings(), system="s", user="u", output_model=Answer)
    assert (result.output, result.fallback_reason) == (None, "llm_offline")
