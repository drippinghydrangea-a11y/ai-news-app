# Phase 2 サブプロジェクト1: LLM要約・注目度・おすすめ10選 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取得済みの記事をGoogle Gemini API(無料枠)に渡し、日本語要約・注目度(★1〜5)・おすすめ10選フラグを付与して表示する。API失敗時は要約なしのPhase 1相当表示にフォールバックする。

**Architecture:** 新規モジュール`enrich.py`が`fetch_news.get_all_articles()`の出力を受け取り、Gemini APIへ1回のリクエストで全記事をまとめて送信、要約/評価/おすすめを付与して返す。`generate_site.py`はこの結果をテンプレートに渡すだけで、失敗時のフォールバック処理は`enrich.py`内で完結する。

**Tech Stack:** Python 3.12, requests(新規追加), 既存: feedparser, Jinja2, PyYAML, pytest

**Spec:** `docs/superpowers/specs/2026-09-21-phase2-llm-enrichment-design.md`

## Global Constraints

- Gemini APIエンドポイント: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}`(モデルは`gemini-flash-latest`、`generationConfig.response_mime_type`を`application/json`に設定してJSON出力を強制、タイムアウト30秒)
- APIキーは環境変数`GEMINI_API_KEY`から読む(ローカル)/GitHub Secret(CI)。未設定なら即座にフォールバックしAPI呼び出しは行わない
- LLM呼び出し失敗(キー未設定・ネットワークエラー・レスポンス形式不正)は例外を投げず、各記事に`summary=None, star=None, recommended=False`を付与してフォールバックする。サイト全体の更新は止めない
- `recommended=true`は最大10件。LLMがそれ以上返した場合は`star`降順で上位10件のみを残し、他は`false`に強制する
- 新規SDKは追加しない(`requests`のみ追加)。全記事を1回のAPI呼び出しにまとめる(記事数分の呼び出しをしない)
- 既読/未読の判定ロジック(localStorage、記事リンクURLをキー)は変更しない。おすすめタブは`recommended=true`のみでフィルタし、既読状態とは独立して表示する

---

## File Structure

```
ai_news_app/
├── enrich.py                     # 新規: Gemini API呼び出し・要約/評価/おすすめ付与
├── generate_site.py               # 変更: main()でenrich_articlesを呼ぶ
├── requirements.txt                # 変更: requestsを追加
├── templates/
│   └── index.html.j2               # 変更: おすすめタブ・要約/星表示・JS拡張
├── tests/
│   ├── test_enrich.py               # 新規
│   ├── test_generate_site.py        # 変更
│   └── test_workflow_yaml.py        # 変更
└── .github/
    └── workflows/
        └── update-news.yml          # 変更: GEMINI_API_KEY env追加
```

---

### Task 1: `enrich.py`基盤(プロンプト生成・API呼び出し・レスポンス解析)

**Files:**
- Modify: `requirements.txt`
- Create: `enrich.py`
- Create: `tests/test_enrich.py`

**Interfaces:**
- Produces: `_build_prompt(articles: list[dict]) -> str`、`_call_gemini(prompt: str, api_key: str) -> str`、`_parse_enrichment(text: str, expected_count: int) -> list[dict]`(各要素は`summary`/`star`/`recommended`キーを持つ辞書。件数不一致・形式不正時は`ValueError`を送出)
- これらはTask 2の`enrich_articles`が消費する

- [ ] **Step 0: `requirements.txt`に`requests`を追加し依存関係をインストール**

`requirements.txt`:
```
feedparser
jinja2
pyyaml
requests
```

Run: `pip install -r requirements-dev.txt`
Expected: エラーなくインストール完了

- [ ] **Step 1: `_build_prompt`の失敗するテストを書く**

`tests/test_enrich.py`を新規作成:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_build_prompt_includes_source_and_title -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'enrich'`)

- [ ] **Step 3: `enrich.py`を作成し`_build_prompt`を実装**

```python
def _build_prompt(articles):
    lines = [
        f"{i}. [{article['source']}] {article['title']}"
        for i, article in enumerate(articles)
    ]
    articles_block = "\n".join(lines)
    return (
        "あなたはAIニュースのキュレーターです。以下はRSSから取得したAI関連ニュースの一覧です。"
        "各記事について、日本語で1〜2文の要約(summary)、注目度を1〜5の整数で評価したもの(star)、"
        "そして全体の中で特に重要だと思う記事を最大10件選んで recommended を true にしてください"
        "(それ以外は false)。\n\n"
        f"{articles_block}\n\n"
        "出力は必ず、入力と同じ順序・同じ件数のJSON配列のみとしてください。"
        "各要素は {\"summary\": string, \"star\": integer, \"recommended\": boolean} の形式です。"
        "他の説明文は一切含めないでください。"
    )
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_build_prompt_includes_source_and_title -v`
Expected: PASS

- [ ] **Step 5: `_parse_enrichment`の正常系の失敗するテストを書く**

```python
def test_parse_enrichment_returns_list_for_valid_json():
    text = '[{"summary": "要約A", "star": 4, "recommended": true}, {"summary": "要約B", "star": 2, "recommended": false}]'

    result = enrich._parse_enrichment(text, expected_count=2)

    assert result == [
        {"summary": "要約A", "star": 4, "recommended": True},
        {"summary": "要約B", "star": 2, "recommended": False},
    ]
```

- [ ] **Step 6: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_returns_list_for_valid_json -v`
Expected: FAIL(`AttributeError: module 'enrich' has no attribute '_parse_enrichment'`)

- [ ] **Step 7: `_parse_enrichment`を最小実装(検証なし)**

`enrich.py`の先頭に`import json`を追加し、以下を追記:

```python
import json


def _parse_enrichment(text, expected_count):
    return json.loads(text)
```

- [ ] **Step 8: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_returns_list_for_valid_json -v`
Expected: PASS

- [ ] **Step 9: 件数不一致で例外を送出することを確認する失敗するテストを書く**

```python
def test_parse_enrichment_raises_on_count_mismatch():
    text = '[{"summary": "A", "star": 3, "recommended": false}]'

    with pytest.raises(ValueError):
        enrich._parse_enrichment(text, expected_count=2)
```

- [ ] **Step 10: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_raises_on_count_mismatch -v`
Expected: FAIL(`ValueError`が送出されずテストが失敗する)

- [ ] **Step 11: 件数検証を追加**

`enrich.py`の`_parse_enrichment`を書き換える:

```python
def _parse_enrichment(text, expected_count):
    parsed = json.loads(text)
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        raise ValueError(
            f"Expected a JSON array of {expected_count} items, got: {parsed!r}"
        )
    return parsed
```

- [ ] **Step 12: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_raises_on_count_mismatch -v`
Expected: PASS

- [ ] **Step 13: 不正な要素形式で例外を送出することを確認する失敗するテストを書く**

```python
def test_parse_enrichment_raises_on_malformed_item():
    text = '[{"summary": "A", "star": 3}]'

    with pytest.raises(ValueError):
        enrich._parse_enrichment(text, expected_count=1)
```

- [ ] **Step 14: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_raises_on_malformed_item -v`
Expected: FAIL(`recommended`キーが無くても現状の実装はエラーにしないため、ValueErrorが送出されない)

- [ ] **Step 15: 要素の形式検証を追加**

`enrich.py`の`_parse_enrichment`を書き換える:

```python
def _parse_enrichment(text, expected_count):
    parsed = json.loads(text)
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        raise ValueError(
            f"Expected a JSON array of {expected_count} items, got: {parsed!r}"
        )
    for item in parsed:
        if not isinstance(item, dict) or not {"summary", "star", "recommended"} <= item.keys():
            raise ValueError(f"Malformed enrichment item: {item!r}")
    return parsed
```

- [ ] **Step 16: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_parse_enrichment_raises_on_malformed_item -v`
Expected: PASS

- [ ] **Step 17: `_call_gemini`の失敗するテストを書く**

```python
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
```

- [ ] **Step 18: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_call_gemini_returns_text_from_response -v`
Expected: FAIL(`AttributeError: module 'enrich' has no attribute 'requests'`。`enrich.py`がまだ`requests`をimportしていないため)

- [ ] **Step 19: `_call_gemini`を実装**

`enrich.py`の先頭に`import requests`を追加し、モデル定数と関数を追記:

```python
import requests

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT_SECONDS = 30


def _call_gemini(prompt, api_key):
    response = requests.post(
        GEMINI_API_URL,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        },
        timeout=GEMINI_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
```

- [ ] **Step 20: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_call_gemini_returns_text_from_response -v`
Expected: PASS

- [ ] **Step 21: `tests/test_enrich.py`全体を実行**

Run: `pytest tests/test_enrich.py -v`
Expected: 全てPASS

- [ ] **Step 22: コミット**

```bash
git add requirements.txt enrich.py tests/test_enrich.py
git commit -m "feat: add Gemini API prompt building, calling, and response parsing"
```

---

### Task 2: `enrich_articles`オーケストレーション・フォールバック・上位10件ガード

**Files:**
- Modify: `enrich.py`
- Modify: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `_build_prompt`, `_call_gemini`, `_parse_enrichment`(Task 1)
- Produces: `enrich_articles(articles: list[dict]) -> list[dict]`(各記事に`summary`/`star`/`recommended`を追加したコピーを返す。例外を投げない)。Task 3の`generate_site.py`がこれを消費する

- [ ] **Step 1: APIキー未設定時にフォールバックすることを確認する失敗するテストを書く**

`tests/test_enrich.py`に追記:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_falls_back_when_api_key_missing -v`
Expected: FAIL(`AttributeError: module 'enrich' has no attribute 'enrich_articles'`)

- [ ] **Step 3: `enrich_articles`を最小実装(APIキー未設定時のフォールバックのみ)**

`enrich.py`に`import os`を追加し、以下を追記:

```python
import os


def enrich_articles(articles):
    """Enrich articles with an LLM-generated summary, star rating, and
    recommended flag via the Gemini API. On any failure, returns the
    original articles with summary=None, star=None, recommended=False
    so the page can still render without summaries.
    """
    fallback = [
        dict(article, summary=None, star=None, recommended=False)
        for article in articles
    ]

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback

    return fallback
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_falls_back_when_api_key_missing -v`
Expected: PASS

- [ ] **Step 5: 成功時にenrichmentが付与されることを確認する失敗するテストを書く**

```python
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
```

- [ ] **Step 6: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_returns_enriched_data_on_success -v`
Expected: FAIL(APIキーがある場合も現状の実装は`fallback`をそのまま返すため、`summary`が`None`のままで一致しない)

- [ ] **Step 7: 成功パスを実装**

`enrich.py`の`enrich_articles`を書き換える:

```python
def enrich_articles(articles):
    """Enrich articles with an LLM-generated summary, star rating, and
    recommended flag via the Gemini API. On any failure, returns the
    original articles with summary=None, star=None, recommended=False
    so the page can still render without summaries.
    """
    fallback = [
        dict(article, summary=None, star=None, recommended=False)
        for article in articles
    ]

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback

    prompt = _build_prompt(articles)
    text = _call_gemini(prompt, api_key)
    enrichment = _parse_enrichment(text, len(articles))

    enriched = []
    for article, item in zip(articles, enrichment):
        enriched.append(dict(
            article,
            summary=item.get("summary"),
            star=item.get("star"),
            recommended=bool(item.get("recommended")),
        ))
    return enriched
```

- [ ] **Step 8: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_returns_enriched_data_on_success -v`
Expected: PASS

- [ ] **Step 9: API呼び出し例外時にフォールバックすることを確認する失敗するテストを書く**

```python
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
```

- [ ] **Step 10: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_falls_back_on_exception -v`
Expected: FAIL(`TimeoutError`がそのまま送出され、テストがエラー終了する)

- [ ] **Step 11: try/exceptで例外を捕捉してフォールバック**

`enrich.py`の先頭に`import logging`を追加し`logger = logging.getLogger(__name__)`を定義、`enrich_articles`を書き換える:

```python
import logging

logger = logging.getLogger(__name__)


def enrich_articles(articles):
    """Enrich articles with an LLM-generated summary, star rating, and
    recommended flag via the Gemini API. On any failure, returns the
    original articles with summary=None, star=None, recommended=False
    so the page can still render without summaries.
    """
    fallback = [
        dict(article, summary=None, star=None, recommended=False)
        for article in articles
    ]

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback

    try:
        prompt = _build_prompt(articles)
        text = _call_gemini(prompt, api_key)
        enrichment = _parse_enrichment(text, len(articles))
    except Exception:
        logger.warning("Gemini enrichment failed; falling back to unenriched articles", exc_info=True)
        return fallback

    enriched = []
    for article, item in zip(articles, enrichment):
        enriched.append(dict(
            article,
            summary=item.get("summary"),
            star=item.get("star"),
            recommended=bool(item.get("recommended")),
        ))
    return enriched
```

- [ ] **Step 12: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_falls_back_on_exception -v`
Expected: PASS

- [ ] **Step 13: 空リストでAPI呼び出しをしないことを確認する失敗するテストを書く**

例外が`enrich_articles`内で捕捉されてしまい、単に`result == []`だけを見るテストでは「呼ばれていないこと」を正しく検証できない(内部のtry/exceptに握りつぶされてテストが誤ってPASSしてしまう)。呼び出し回数を外部から観測できるようにする:

```python
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
```

- [ ] **Step 14: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_handles_empty_list -v`
Expected: FAIL(`assert calls == []`の部分で失敗する。`calls == [1]`になっているはず。現状の実装は空リストでも`_call_gemini`まで進んでしまい、内部でAssertionErrorが送出され`except Exception`に捕捉されて`fallback`(=`[]`)が返るため、`result == []`は通ってしまうが呼び出し自体は発生している)

- [ ] **Step 15: 空リストの早期リターンを追加**

`enrich.py`の`enrich_articles`の冒頭に追記:

```python
def enrich_articles(articles):
    """..."""
    fallback = [
        dict(article, summary=None, star=None, recommended=False)
        for article in articles
    ]

    if not articles:
        return fallback

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback

    try:
        prompt = _build_prompt(articles)
        text = _call_gemini(prompt, api_key)
        enrichment = _parse_enrichment(text, len(articles))
    except Exception:
        logger.warning("Gemini enrichment failed; falling back to unenriched articles", exc_info=True)
        return fallback

    enriched = []
    for article, item in zip(articles, enrichment):
        enriched.append(dict(
            article,
            summary=item.get("summary"),
            star=item.get("star"),
            recommended=bool(item.get("recommended")),
        ))
    return enriched
```

- [ ] **Step 16: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_handles_empty_list -v`
Expected: PASS

- [ ] **Step 17: おすすめ11件以上を上位10件に絞ることを確認する失敗するテストを書く**

```python
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
```

(`T0`はstar=1、`T1`はstar=2で最も注目度が低い2件。上位10件=`T2`〜`T11`が残るはず)

- [ ] **Step 18: テストが失敗することを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_caps_recommended_to_top_ten_by_star -v`
Expected: FAIL(12件全てが`recommended=True`のまま返るため、`recommended_titles`に`T0`/`T1`も含まれてしまう)

- [ ] **Step 19: 上位10件ガードを実装**

`enrich.py`の先頭付近に定数を追加し、`enrich_articles`の`try`ブロック直後(`enriched = []`より前)に絞り込み処理を追加する:

```python
TOP_RECOMMENDED_COUNT = 10
```

```python
    try:
        prompt = _build_prompt(articles)
        text = _call_gemini(prompt, api_key)
        enrichment = _parse_enrichment(text, len(articles))
    except Exception:
        logger.warning("Gemini enrichment failed; falling back to unenriched articles", exc_info=True)
        return fallback

    recommended_indices = [i for i, item in enumerate(enrichment) if item.get("recommended")]
    if len(recommended_indices) > TOP_RECOMMENDED_COUNT:
        recommended_indices.sort(key=lambda i: enrichment[i].get("star") or 0, reverse=True)
        keep = set(recommended_indices[:TOP_RECOMMENDED_COUNT])
        for i, item in enumerate(enrichment):
            if i not in keep:
                item["recommended"] = False

    enriched = []
    for article, item in zip(articles, enrichment):
        enriched.append(dict(
            article,
            summary=item.get("summary"),
            star=item.get("star"),
            recommended=bool(item.get("recommended")),
        ))
    return enriched
```

- [ ] **Step 20: テストが通ることを確認**

Run: `pytest tests/test_enrich.py::test_enrich_articles_caps_recommended_to_top_ten_by_star -v`
Expected: PASS

- [ ] **Step 21: `tests/test_enrich.py`全体を実行**

Run: `pytest tests/test_enrich.py -v`
Expected: 全てPASS(8テスト)

- [ ] **Step 22: コミット**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat: orchestrate Gemini enrichment with fallback and top-10 cap"
```

---

### Task 3: `generate_site.py`統合

**Files:**
- Modify: `generate_site.py`
- Modify: `tests/test_generate_site.py`

**Interfaces:**
- Consumes: `enrich.enrich_articles(articles) -> list[dict]`(Task 2)
- Produces: `main()`が`enrich_articles`を呼んでから`render_html`に渡す。Task 4のテンプレートがこの拡張済み記事データ(`summary`/`star`/`recommended`キー付き)を消費する

- [ ] **Step 1: `main`が`enrich_articles`を呼ぶことを確認する失敗するテストを書く**

`tests/test_generate_site.py`に追記:

```python
def test_main_enriches_articles_before_rendering(monkeypatch, tmp_path):
    sample = [
        {"title": "T", "link": "https://x/1", "source": "S", "published_display": "d"},
    ]
    enriched_sample = [
        dict(sample[0], summary="要約", star=4, recommended=True),
    ]
    captured = {}

    def fake_enrich(articles):
        captured["articles"] = articles
        return enriched_sample

    monkeypatch.setattr(generate_site, "get_all_articles", lambda path: sample)
    monkeypatch.setattr(generate_site, "enrich_articles", fake_enrich)
    output_path = tmp_path / "index.html"
    monkeypatch.setattr(generate_site, "OUTPUT_PATH", output_path)

    generate_site.main()

    assert captured["articles"] == sample
    assert output_path.exists()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_main_enriches_articles_before_rendering -v`
Expected: FAIL(`generate_site`モジュールに`enrich_articles`という属性が無いため、`monkeypatch.setattr`がAttributeErrorを送出する)

- [ ] **Step 3: `generate_site.py`に`enrich_articles`の呼び出しを追加**

`generate_site.py`の先頭のimportに追記:

```python
from enrich import enrich_articles
```

`main()`を書き換える:

```python
def main():
    articles = get_all_articles(str(FEEDS_CONFIG))
    if not articles:
        print(
            "No articles fetched from any feed; leaving docs/index.html unchanged.",
            file=sys.stderr,
        )
        sys.exit(1)

    enriched = enrich_articles(articles)

    generated_at_display = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    html = render_html(enriched, generated_at_display)
    write_site(html, OUTPUT_PATH)
    print(f"Wrote {len(enriched)} articles to {OUTPUT_PATH}")
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_main_enriches_articles_before_rendering -v`
Expected: PASS

- [ ] **Step 5: `tests/test_generate_site.py`全体を実行**

Run: `pytest tests/test_generate_site.py -v`
Expected: 全てPASS(既存の`test_main_exits_when_no_articles`・`test_main_writes_site_on_success`も、`enrich_articles`が実体としてimportされて呼ばれるようになるため、`GEMINI_API_KEY`未設定環境下では自動的にフォールバックが動作し壊れないことを確認する。もし環境変数`GEMINI_API_KEY`がテスト実行環境にたまたま設定されていて既存テストが不安定になる場合は、該当テストの冒頭に`monkeypatch.delenv("GEMINI_API_KEY", raising=False)`を追加すること)

- [ ] **Step 6: コミット**

```bash
git add generate_site.py tests/test_generate_site.py
git commit -m "feat: call Gemini enrichment from generate_site.main"
```

---

### Task 4: テンプレート変更(おすすめタブ・要約/星表示)

**Files:**
- Modify: `templates/index.html.j2`
- Modify: `tests/test_generate_site.py`

**Interfaces:**
- Consumes: 各記事dictが`summary`(str|None)、`star`(int|None)、`recommended`(bool)キーを持つこと(Task 2/3)
- Produces: 3タブ構成(未読/既読/おすすめ)のHTML。他タスクからの依存なし(最終タスク)

- [ ] **Step 1: 要約・星が表示されることを確認する失敗するテストを書く**

`tests/test_generate_site.py`に追記:

```python
def test_render_html_shows_summary_and_star_when_present():
    articles = [
        {
            "title": "T", "link": "https://x/1", "source": "S", "published_display": "d",
            "summary": "これは要約です", "star": 3, "recommended": True,
        }
    ]

    html = generate_site.render_html(articles, "now")

    assert "これは要約です" in html
    assert "★★★☆☆" in html
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_shows_summary_and_star_when_present -v`
Expected: FAIL(テンプレートがまだ`summary`/`star`を出力しないため、両方とも`html`に含まれない)

- [ ] **Step 3: テンプレートに要約・星の表示を追加**

`templates/index.html.j2`の`<style>`内、`.date`のルールの直後に追記:

```css
  .summary { font-size: 0.88rem; color: var(--text); margin-top: 8px; line-height: 1.5; }
  .stars { font-size: 0.85rem; color: var(--accent); margin-top: 6px; letter-spacing: 1px; }
```

`.card`内、`<div class="date">...</div>`の直後に追記:

```html
    {% if article.summary %}
    <div class="summary">{{ article.summary }}</div>
    {% endif %}
    {% if article.star %}
    <div class="stars">{{ '★' * article.star }}{{ '☆' * (5 - article.star) }}</div>
    {% endif %}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_shows_summary_and_star_when_present -v`
Expected: PASS

- [ ] **Step 5: 要約・星が無い場合は非表示のままであることを確認するテストを書く**

```python
def test_render_html_hides_summary_and_star_when_absent():
    articles = [
        {
            "title": "T", "link": "https://x/1", "source": "S", "published_display": "d",
            "summary": None, "star": None, "recommended": False,
        }
    ]

    html = generate_site.render_html(articles, "now")

    assert 'class="summary"' not in html
    assert 'class="stars"' not in html
```

- [ ] **Step 6: テストを実行して確認**

Run: `pytest tests/test_generate_site.py::test_render_html_hides_summary_and_star_when_absent -v`
Expected: PASS(Step 3のJinja条件式が`None`と`0`のどちらも偽と評価するため、追加の実装なしでこの時点で既にPASSするはず。これはTask 3で追加したロジックの分岐を確認する回帰テストであり、新規コードを駆動するものではない)

- [ ] **Step 7: おすすめタブとdata-recommended属性を確認する失敗するテストを書く**

```python
def test_render_html_includes_recommended_tab_and_attribute():
    articles = [
        {
            "title": "T", "link": "https://x/1", "source": "S", "published_display": "d",
            "summary": None, "star": None, "recommended": True,
        }
    ]

    html = generate_site.render_html(articles, "now")

    assert 'data-view="recommended"' in html
    assert 'data-recommended="true"' in html
```

- [ ] **Step 8: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_includes_recommended_tab_and_attribute -v`
Expected: FAIL(おすすめタブのボタンも`data-recommended`属性もまだ存在しない)

- [ ] **Step 9: おすすめタブ・属性・CSS・JSを追加**

`templates/index.html.j2`の`.tabs`直下のボタン2つに続けて3つ目を追加:

```html
  <div class="tabs">
    <button class="tab-btn active" data-view="unread" type="button">未読</button>
    <button class="tab-btn" data-view="read" type="button">既読</button>
    <button class="tab-btn" data-view="recommended" type="button">おすすめ</button>
  </div>
```

`.card`の`data-link`属性の隣に`data-recommended`を追加:

```html
  <div class="card" data-link="{{ article.link }}" data-recommended="{{ 'true' if article.recommended else 'false' }}">
```

CSSの既存フィルタルールの直後に追記:

```css
  body[data-view="recommended"] .card:not([data-recommended="true"]) { display: none; }
```

JS内の`updateEmptyState`関数を書き換える(3方向分岐に対応):

```javascript
    function updateEmptyState() {
      var view = document.body.getAttribute('data-view');
      var visibleCount = cards.filter(function (card) {
        if (view === 'read') return card.classList.contains('is-read');
        if (view === 'recommended') return card.getAttribute('data-recommended') === 'true';
        return !card.classList.contains('is-read');
      }).length;
      emptyState.hidden = visibleCount !== 0;
      var messages = {
        unread: 'すべて既読です 🎉',
        read: 'まだ既読の記事がありません',
        recommended: 'おすすめ記事がありません',
      };
      emptyState.textContent = messages[view] || '';
    }
```

- [ ] **Step 10: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_includes_recommended_tab_and_attribute -v`
Expected: PASS

- [ ] **Step 11: `tests/test_generate_site.py`全体を実行**

Run: `pytest tests/test_generate_site.py -v`
Expected: 全てPASS

- [ ] **Step 12: コミット**

```bash
git add templates/index.html.j2 tests/test_generate_site.py
git commit -m "feat: add recommended tab, summary, and star display to the news page"
```

---

### Task 5: ワークフローに`GEMINI_API_KEY`を追加

**Files:**
- Modify: `.github/workflows/update-news.yml`
- Modify: `tests/test_workflow_yaml.py`

**Interfaces:**
- Consumes: なし
- Produces: `generate_site.py`実行ステップに`GEMINI_API_KEY`環境変数が設定されたワークフロー。Task 6のGitHub Secret設定が実際に機能するための前提

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_workflow_yaml.py`に追記(ファイル冒頭の`from pathlib import Path`・`import yaml`はそのまま使う):

```python
def test_generate_site_step_has_gemini_api_key_env():
    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "update-news.yml"
    )

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = yaml.safe_load(f)

    steps = workflow["jobs"]["update"]["steps"]
    generate_step = next(s for s in steps if s.get("run") == "python generate_site.py")

    assert generate_step["env"]["GEMINI_API_KEY"] == "${{ secrets.GEMINI_API_KEY }}"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_workflow_yaml.py::test_generate_site_step_has_gemini_api_key_env -v`
Expected: FAIL(`KeyError: 'env'`。該当ステップに`env`キーがまだ無い)

- [ ] **Step 3: ワークフローに`env`を追加**

`.github/workflows/update-news.yml`の`- run: python generate_site.py`の行を書き換える:

```yaml
      - run: python generate_site.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_workflow_yaml.py::test_generate_site_step_has_gemini_api_key_env -v`
Expected: PASS

- [ ] **Step 5: `tests/test_workflow_yaml.py`全体を実行**

Run: `pytest tests/test_workflow_yaml.py -v`
Expected: 全てPASS

- [ ] **Step 6: コミット**

```bash
git add .github/workflows/update-news.yml tests/test_workflow_yaml.py
git commit -m "ci: pass GEMINI_API_KEY secret to the site generation step"
```

---

### Task 6: Gemini APIキー取得・ローカル確認・GitHub Secret設定・公開

> ⚠️ このタスクはユーザーによるGoogle AI StudioでのAPIキー発行(外部アカウント操作)と、GitHub Secretsの追加を伴う。APIキー発行はユーザー自身が行う必要がある。

**Files:**
- なし(設定・動作確認)

**Interfaces:**
- Consumes: Task 1〜5で作成した全モジュール一式
- Produces: 実際にGemini APIで要約・星・おすすめが付与された`docs/index.html`。GitHub Secretsへの`GEMINI_API_KEY`登録

- [ ] **Step 1: ユーザーにGemini APIキーの発行を依頼**

ユーザーに次のURLでAPIキーを発行してもらう: `https://aistudio.google.com/apikey`(Googleアカウントでログインし、「Create API key」をクリック)。発行されたキーをチャットで受け取る。

- [ ] **Step 2: ローカルで環境変数を設定し実データで動作確認**

```bash
export GEMINI_API_KEY="<受け取ったキー>"
pytest -v
python generate_site.py
```

Expected: 全テストPASS。`generate_site.py`が正常終了し、`docs/index.html`に要約・★・おすすめタブが実際に反映されていることを目視確認する(`grep -c 'class="summary"' docs/index.html`などで件数を確認してもよい)。

- [ ] **Step 3: GitHub SecretsにAPIキーを登録**

```bash
printf '%s' "<受け取ったキー>" | gh secret set GEMINI_API_KEY --repo drippinghydrangea-a11y/ai-news-app
```

(シェル履歴にキーの値が残らないよう、`--body`フラグではなく標準入力経由で渡す)

Expected: `✓ Set Actions secret GEMINI_API_KEY for drippinghydrangea-a11y/ai-news-app`のような成功メッセージ

- [ ] **Step 4: 変更をpushし、ワークフローを手動トリガーして確認**

```bash
git push origin master:main
gh workflow run update-news.yml --repo drippinghydrangea-a11y/ai-news-app
```

数十秒待ってから:

```bash
gh run list --workflow=update-news.yml --repo drippinghydrangea-a11y/ai-news-app --limit 1
```

Expected: `completed`/`success`

- [ ] **Step 5: 公開サイトで最終確認**

`https://drippinghydrangea-a11y.github.io/ai-news-app/` をブラウザ(またはcurlで生HTML)で開き、以下を確認する:
- 「おすすめ」タブが表示され、クリックすると最大10件の記事が表示される
- 各記事カードに要約文と★評価が表示されている
- 既読/未読タブの動作(Phase 2サブプロジェクト2)に影響が出ていない

- [ ] **Step 6: 完了報告**

ユーザーに結果を報告する。Gemini APIの無料枠には日次/分間のレート制限があるため、その旨と、制限に達した日は自動的に要約なし表示にフォールバックすることを伝える。
