from crawler.transport import TransportError, Outcome, classify_exception
from crawler import transport
import pytest
import json
from urllib.error import HTTPError


def test_classification_preserves_typed_network_errors():
    assert classify_exception(TransportError(Outcome.NETWORK, "timed out", True)) == Outcome.NETWORK


def test_network_attempt_has_timeout_and_no_hidden_retries(monkeypatch):
    calls = []

    def timeout(request, **kwargs):
        calls.append(kwargs)
        raise TimeoutError("timed out")

    monkeypatch.setattr(transport, "urlopen", timeout)
    with pytest.raises(TransportError) as error:
        transport.fetch_reviews_page("com.x", "en", "us", 20, None)
    assert error.value.outcome == Outcome.NETWORK
    assert error.value.retryable
    assert len(calls) == 1
    assert calls[0]["timeout"] == 20


def test_single_page_parser_preserves_cursor(monkeypatch):
    payload = [["raw-review"], ["next-page"], None]
    body = ")]}'\n\n" + json.dumps([["wrb.fr", "rpc", json.dumps(payload)]])
    monkeypatch.setattr(transport, "fetch_text", lambda *a: body)
    assert transport._fetch_review_items("url", "com.x", 2, 20, None, None, None) == (
        ["raw-review"], "next-page",
    )


@pytest.mark.parametrize("code,outcome", [(404, Outcome.NOT_FOUND), (429, Outcome.THROTTLED),
                                         (503, Outcome.NETWORK), (400, Outcome.TERMINAL)])
def test_http_error_classification(code, outcome):
    assert classify_exception(HTTPError("url", code, "error", {}, None)) == outcome


def test_app_details_preserve_country_fallback(monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            raise HTTPError(url, 404, "not found", {}, None)
        return "app body"

    monkeypatch.setattr(transport, "fetch_text", fetch)
    monkeypatch.setattr(transport, "parse_dom", lambda *a: {"title": "App title"})
    assert transport.fetch_app_details("com.x")["title"] == "App title"
    assert len(calls) == 2
