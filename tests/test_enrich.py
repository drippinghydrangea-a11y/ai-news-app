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
