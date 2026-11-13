from intelligence.genai_client import (
    DEFAULT_GEMINI_RETRY_ATTEMPTS,
    DEFAULT_GEMINI_TIMEOUT_MS,
    build_gemini_http_options,
    create_genai_client,
)


class FakeTypes:
    class HttpRetryOptions:
        def __init__(self, **kwargs):
            self.values = kwargs

    class HttpOptions:
        def __init__(self, **kwargs):
            self.values = kwargs


class FakeGenAI:
    def __init__(self):
        self.arguments = None

    def Client(self, **kwargs):
        self.arguments = kwargs
        return {"client": "fake"}


def test_gemini_http_options_have_finite_timeout_and_transient_retries(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_MS", "60000")
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "3")
    options = build_gemini_http_options(types_module=FakeTypes)
    assert options.values["timeout"] == 60000
    retry = options.values["retry_options"]
    assert retry.values["attempts"] == 3
    assert retry.values["http_status_codes"] == [408, 429, 500, 502, 503, 504]
    assert retry.values["max_delay"] == 3.0


def test_gemini_http_options_bound_invalid_environment_values(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_MS", "not-a-number")
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "99")
    options = build_gemini_http_options(types_module=FakeTypes)
    assert options.values["timeout"] == DEFAULT_GEMINI_TIMEOUT_MS
    assert options.values["retry_options"].values["attempts"] == 5


def test_gemini_client_is_lazy_and_requires_nonempty_api_key():
    fake = FakeGenAI()
    assert create_genai_client("", genai_module=fake, types_module=FakeTypes) is None
    result = create_genai_client(" test-key ", genai_module=fake, types_module=FakeTypes)
    assert result == {"client": "fake"}
    assert fake.arguments["api_key"] == "test-key"
    assert fake.arguments["http_options"].values["timeout"] == DEFAULT_GEMINI_TIMEOUT_MS
