from types import SimpleNamespace

import pytest

from intelligence.web_research import (
    format_grounded_answer,
    generate_web_research_response,
    is_web_research_request,
)


class FakeTypes:
    class GoogleSearch:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Tool:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    class Models:
        def __init__(self, owner):
            self.owner = owner

        def generate_content(self, **kwargs):
            self.owner.calls.append(kwargs)
            return self.owner.response

    @property
    def models(self):
        return self.Models(self)


def grounded_response(text, sources):
    chunks = []
    for title, uri in sources:
        chunks.append(SimpleNamespace(web=SimpleNamespace(title=title, uri=uri)))
    metadata = SimpleNamespace(grounding_chunks=chunks)
    candidate = SimpleNamespace(grounding_metadata=metadata)
    return SimpleNamespace(text=text, candidates=[candidate])


@pytest.mark.parametrize(
    "command",
    [
        "Search the web for Windows 11 requirements",
        "What are the latest IT layoffs?",
        "Tell me recent updates about Python",
        "What is the current version of this package?",
        "Show today's news about technology",
    ],
)
def test_current_information_requests_are_detected(command):
    assert is_web_research_request(command)


@pytest.mark.parametrize(
    "command",
    [
        "What time is it?",
        "take a note buy milk",
        "open chrome",
        "system status",
    ],
)
def test_ordinary_local_commands_do_not_trigger_web_research(command):
    assert not is_web_research_request(command)


def test_web_research_uses_google_search_grounding_and_includes_sources():
    response = grounded_response(
        "A current summary.",
        [
            ("Official release notes", "https://example.com/release"),
            ("Security advisory", "https://example.com/security"),
        ],
    )
    client = FakeClient(response)

    answer = generate_web_research_response(
        client=client,
        query="What is the latest release?",
        types_module=FakeTypes,
    )

    assert "A current summary." in answer
    assert "[1] Official release notes — https://example.com/release" in answer
    assert "[2] Security advisory — https://example.com/security" in answer
    call = client.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"].tools[0].google_search is not None
    assert "untrusted data" in call["config"].system_instruction


def test_unsafe_urls_are_omitted_from_grounding_sources():
    response = grounded_response(
        "A summary.",
        [
            ("Bad scheme", "javascript:alert(1)"),
            ("Relative", "/some/path"),
            ("Good source", "https://example.com/good"),
        ],
    )
    answer = format_grounded_answer(response)

    assert "https://example.com/good" in answer
    assert "javascript:" not in answer
    assert "/some/path" not in answer


def test_duplicate_source_links_are_only_shown_once_and_source_count_is_bounded():
    many_sources = [
        (f"Source {index}", f"https://example.com/{index}")
        for index in range(10)
    ]
    many_sources.insert(1, ("Repeated", "https://example.com/0"))
    answer = format_grounded_answer(grounded_response("Summary.", many_sources))

    assert answer.count("https://example.com/0") == 1
    assert "[5] Source 4 — https://example.com/4" in answer
    assert "https://example.com/5" not in answer


def test_missing_grounding_metadata_discloses_that_sources_could_not_be_verified():
    answer = format_grounded_answer(SimpleNamespace(text="Plain answer.", candidates=[]))
    assert "Plain answer." in answer
    assert "couldn't verify source links" in answer


def test_empty_query_is_rejected_before_calling_provider():
    client = FakeClient(SimpleNamespace(text="unused", candidates=[]))
    with pytest.raises(ValueError, match="query"):
        generate_web_research_response(
            client=client,
            query=" ",
            types_module=FakeTypes,
        )
    assert client.calls == []
