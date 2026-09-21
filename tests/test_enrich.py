import json

import pytest

import enrich


def test_build_prompt_includes_source_and_title():
    articles = [
        {"source": "ITmedia AI+", "title": "記事A", "link": "https://x/1", "published_display": "d"},
        {"source": "AINOW", "title": "記事B", "link": "https://x/2", "published_display": "d"},
    ]

    prompt = enrich._build_prompt(articles)

    assert "ITmedia AI+" in prompt
    assert "記事A" in prompt
    assert "AINOW" in prompt
    assert "記事B" in prompt


def test_parse_enrichment_returns_list_for_valid_json():
    text = '[{"summary": "要約A", "star": 4, "recommended": true}, {"summary": "要約B", "star": 2, "recommended": false}]'

    result = enrich._parse_enrichment(text, expected_count=2)

    assert result == [
        {"summary": "要約A", "star": 4, "recommended": True},
        {"summary": "要約B", "star": 2, "recommended": False},
    ]


def test_parse_enrichment_raises_on_count_mismatch():
    text = '[{"summary": "A", "star": 3, "recommended": false}]'

    with pytest.raises(ValueError):
        enrich._parse_enrichment(text, expected_count=2)


def test_parse_enrichment_raises_on_malformed_item():
    text = '[{"summary": "A", "star": 3}]'

    with pytest.raises(ValueError):
        enrich._parse_enrichment(text, expected_count=1)


def test_call_gemini_returns_text_from_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(enrich.requests, "post", fake_post)

    text = enrich._call_gemini("プロンプト", "fake-api-key")

    assert text == "hello"
    assert captured["params"] == {"key": "fake-api-key"}
    assert captured["timeout"] == 30
    assert captured["json"]["contents"][0]["parts"][0]["text"] == "プロンプト"
    assert captured["json"]["generationConfig"]["response_mime_type"] == "application/json"


def test_enrich_articles_falls_back_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("requests.post should not be called without an API key")

    monkeypatch.setattr(enrich.requests, "post", fail_if_called)

    articles = [{"source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d"}]

    result = enrich.enrich_articles(articles)

    assert result == [
        {
            "source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d",
            "summary": None, "star": None, "recommended": False,
        }
    ]


def test_enrich_articles_returns_enriched_data_on_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps([
                        {"summary": "要約A", "star": 5, "recommended": True},
                    ])}]}
                }]
            }

    monkeypatch.setattr(enrich.requests, "post", lambda *a, **kw: FakeResponse())

    articles = [{"source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d"}]

    result = enrich.enrich_articles(articles)

    assert result == [
        {
            "source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d",
            "summary": "要約A", "star": 5, "recommended": True,
        }
    ]


def test_enrich_articles_falls_back_on_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def raise_error(*args, **kwargs):
        raise TimeoutError("boom")

    monkeypatch.setattr(enrich.requests, "post", raise_error)

    articles = [{"source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d"}]

    result = enrich.enrich_articles(articles)

    assert result == [
        {
            "source": "S1", "title": "T1", "link": "https://x/1", "published_display": "d",
            "summary": None, "star": None, "recommended": False,
        }
    ]


def test_enrich_articles_handles_empty_list(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        raise AssertionError("should not be called")

    monkeypatch.setattr(enrich.requests, "post", fake_post)

    result = enrich.enrich_articles([])

    assert result == []
    assert calls == []


def test_enrich_articles_caps_recommended_to_top_ten_by_star(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    articles = [
        {"source": "S", "title": f"T{i}", "link": f"https://x/{i}", "published_display": "d"}
        for i in range(12)
    ]
    enrichment_items = [
        {"summary": f"要約{i}", "star": i + 1, "recommended": True}
        for i in range(12)
    ]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(enrichment_items)}]}}]}

    monkeypatch.setattr(enrich.requests, "post", lambda *a, **kw: FakeResponse())

    result = enrich.enrich_articles(articles)

    recommended_titles = {a["title"] for a in result if a["recommended"]}
    assert recommended_titles == {f"T{i}" for i in range(2, 12)}
    assert "T0" not in recommended_titles
    assert "T1" not in recommended_titles
