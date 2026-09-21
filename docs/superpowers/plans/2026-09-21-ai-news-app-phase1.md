# AIニュース自動更新アプリ Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RSSフィードから日本語AIニュースを取得し、毎朝自動更新される静的サイトとしてGitHub Pagesで公開する（LLM要約なしのPhase 1）。

**Architecture:** Pythonスクリプトが `feeds.yaml` に列挙されたRSSフィードを取得・重複排除・ソートし、Jinja2テンプレートで `docs/index.html` を生成する。GitHub Actionsの日次cronがこのスクリプトを実行し、変更があればコミット&プッシュする。GitHub Pagesが `docs/` フォルダをそのまま配信する。

**Tech Stack:** Python 3.12, feedparser, Jinja2, PyYAML, pytest, GitHub Actions, GitHub Pages

**Spec:** `docs/superpowers/specs/2026-09-21-ai-news-app-design.md`

## Global Constraints

- 完全無料で運用する(Phase 1ではLLM API呼び出しなし)
- 初期RSSソースは日本語中心、動作確認済みの2件を使う: ITmedia AI+ (`https://rss.itmedia.co.jp/rss/2.0/aiplus.xml`)、AINOW (`https://ainow.ai/feed/`)
- 各ソースにつき直近上位10件(`per_source_limit=10`)まで保持する
- 個別フィードの取得失敗はスキップして継続、全フィード失敗時は `docs/index.html` を上書きしない(非ゼロ終了コードで異常終了)
- 重複記事はリンクURL正規化(スキーム/ホスト小文字化、末尾スラッシュ除去、クエリ・フラグメント除去)とタイトル完全一致の両方で判定し除外する
- GitHub Actionsのcronは毎朝UTC 22時(JST 7時)に実行、`workflow_dispatch` による手動実行にも対応する

---

## File Structure

```
ai_news_app/
├── feeds.yaml                  # RSSフィード一覧
├── fetch_news.py                # フィード取得・重複排除・ソート
├── generate_site.py             # HTML生成
├── requirements.txt              # 実行時依存(feedparser, jinja2, pyyaml)
├── requirements-dev.txt          # テスト依存(pytest)
├── conftest.py                   # pytestがリポジトリルートをimportパスに追加する
├── .gitignore
├── templates/
│   └── index.html.j2             # ニュース一覧テンプレート
├── docs/
│   └── index.html                 # 生成される静的サイト(GitHub Pages配信元)
├── tests/
│   ├── test_fetch_news.py
│   └── test_generate_site.py
└── .github/
    └── workflows/
        └── update-news.yml        # 日次cron + 手動実行ワークフロー
```

---

### Task 1: プロジェクト scaffolding

**Files:**
- Create: `feeds.yaml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `conftest.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `feeds.yaml`(YAMLリスト、各要素は `name`, `url` キー)。以降のタスクの `load_feeds()` がこれを読み込む
- Produces: リポジトリルートがpytestのimportパスに含まれる状態(`conftest.py` 経由)。以降の全テストファイルがこれに依存する

- [ ] **Step 1: `feeds.yaml` を作成**

```yaml
- name: ITmedia AI+
  url: https://rss.itmedia.co.jp/rss/2.0/aiplus.xml
- name: AINOW
  url: https://ainow.ai/feed/
```

- [ ] **Step 2: `requirements.txt` を作成**

```
feedparser
jinja2
pyyaml
```

- [ ] **Step 3: `requirements-dev.txt` を作成**

```
-r requirements.txt
pytest
```

- [ ] **Step 4: `conftest.py` を作成**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 5: `.gitignore` を作成**

```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 6: 依存関係をインストールして動作確認**

Run: `pip install -r requirements-dev.txt`
Expected: エラーなくインストール完了

- [ ] **Step 7: コミット**

```bash
git add feeds.yaml requirements.txt requirements-dev.txt conftest.py .gitignore
git commit -m "chore: scaffold ai_news_app project"
```

---

### Task 2: フィード取得(`load_feeds`, `fetch_feed`)

**Files:**
- Create: `fetch_news.py`
- Test: `tests/test_fetch_news.py`

**Interfaces:**
- Consumes: `feeds.yaml`(Task 1で作成、`name`/`url`キーを持つリストのYAML)
- Produces:
  - `load_feeds(config_path: str) -> list[dict]` — 各要素は `{"name": str, "url": str}`
  - `fetch_feed(name: str, url: str) -> list[dict]` — 各要素は `{"title": str, "link": str, "source": str, "published_parsed": time.struct_time | None, "published_display": str}`(UTC基準、失敗時は空リストを返しログに警告を出す)
  - これらはTask 3の `dedupe_articles` / `sort_and_limit` / `get_all_articles` が消費する

- [ ] **Step 1: `load_feeds` の失敗するテストを書く**

`tests/test_fetch_news.py` を新規作成:

```python
import time

import feedparser

import fetch_news


def test_load_feeds_reads_yaml(tmp_path):
    feeds_path = tmp_path / "feeds.yaml"
    feeds_path.write_text(
        "- name: Source A\n  url: https://a.example.com/rss\n"
        "- name: Source B\n  url: https://b.example.com/rss\n",
        encoding="utf-8",
    )

    feeds = fetch_news.load_feeds(str(feeds_path))

    assert feeds == [
        {"name": "Source A", "url": "https://a.example.com/rss"},
        {"name": "Source B", "url": "https://b.example.com/rss"},
    ]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_load_feeds_reads_yaml -v`
Expected: FAIL(`ModuleNotFoundError` または `AttributeError: module 'fetch_news' has no attribute 'load_feeds'`)

- [ ] **Step 3: `fetch_news.py` を作成し `load_feeds` を実装**

```python
import logging
import time
from urllib.parse import urlsplit, urlunsplit

import feedparser
import yaml

logger = logging.getLogger(__name__)


def load_feeds(config_path):
    """Load feed definitions from a YAML file.

    Returns a list of dicts: {"name": str, "url": str}
    """
    with open(config_path, "r", encoding="utf-8") as f:
        feeds = yaml.safe_load(f)
    return feeds or []
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_fetch_news.py::test_load_feeds_reads_yaml -v`
Expected: PASS

- [ ] **Step 5: `fetch_feed` 成功ケースの失敗するテストを書く**

`tests/test_fetch_news.py` に追記:

```python
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
  <title>Article One</title>
  <link>https://example.com/one</link>
  <pubDate>Mon, 21 Sep 2026 09:00:00 +0900</pubDate>
</item>
<item>
  <title>Article Two</title>
  <link>https://example.com/two</link>
  <pubDate>Sun, 20 Sep 2026 09:00:00 +0900</pubDate>
</item>
</channel>
</rss>
"""


def test_fetch_feed_returns_articles(monkeypatch):
    def fake_parse(url):
        return feedparser.parse(SAMPLE_RSS)

    monkeypatch.setattr(fetch_news.feedparser, "parse", fake_parse)

    articles = fetch_news.fetch_feed("Sample Source", "https://example.com/rss")

    assert len(articles) == 2
    assert articles[0]["title"] == "Article One"
    assert articles[0]["link"] == "https://example.com/one"
    assert articles[0]["source"] == "Sample Source"
    assert articles[0]["published_display"] == "2026-09-21 00:00 UTC"
    assert articles[1]["published_display"] == "2026-09-20 00:00 UTC"
```

- [ ] **Step 6: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_fetch_feed_returns_articles -v`
Expected: FAIL(`AttributeError: module 'fetch_news' has no attribute 'fetch_feed'`)

- [ ] **Step 7: `fetch_feed` と `_entry_to_article` を実装(最小実装、エラーハンドリングはまだ含めない)**

`fetch_news.py` に追記:

```python
def fetch_feed(name, url):
    """Fetch and parse a single RSS feed. Returns a list of article dicts."""
    parsed = feedparser.parse(url)
    return [_entry_to_article(entry, name) for entry in parsed.entries]


def _entry_to_article(entry, source_name):
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if published_parsed:
        published_display = time.strftime("%Y-%m-%d %H:%M UTC", published_parsed)
    else:
        published_display = ""
    return {
        "title": entry.get("title", "(no title)"),
        "link": entry.get("link", ""),
        "source": source_name,
        "published_parsed": published_parsed,
        "published_display": published_display,
    }
```

- [ ] **Step 8: テストが通ることを確認**

Run: `pytest tests/test_fetch_news.py::test_fetch_feed_returns_articles -v`
Expected: PASS

- [ ] **Step 9: `fetch_feed` 失敗ケースの失敗するテストを書く**

```python
class FakeBozoResult:
    bozo = 1
    entries = []
    bozo_exception = Exception("boom")

    def get(self, key, default=None):
        return getattr(self, key, default)


def test_fetch_feed_handles_failure(monkeypatch, caplog):
    def fake_parse(url):
        return FakeBozoResult()

    monkeypatch.setattr(fetch_news.feedparser, "parse", fake_parse)

    with caplog.at_level("WARNING"):
        articles = fetch_news.fetch_feed("Broken Source", "https://example.com/broken")

    assert articles == []
    assert "Broken Source" in caplog.text
```

- [ ] **Step 10: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_fetch_feed_handles_failure -v`
Expected: FAIL(`assert "Broken Source" in caplog.text` の部分で失敗する。Step 7の実装はまだ警告ログを出していないため)

- [ ] **Step 11: `fetch_feed` にbozo(取得失敗)判定とログ出力を追加**

`fetch_news.py` の `fetch_feed` を次のように書き換える:

```python
def fetch_feed(name, url):
    """Fetch and parse a single RSS feed.

    Returns a list of article dicts on success, or an empty list if the
    feed could not be fetched/parsed (a warning is logged in that case).
    """
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Failed to fetch feed %s (%s): %s",
            name, url, parsed.get("bozo_exception"),
        )
        return []

    return [_entry_to_article(entry, name) for entry in parsed.entries]
```

Run: `pytest tests/test_fetch_news.py::test_fetch_feed_handles_failure -v`
Expected: PASS

- [ ] **Step 12: ここまでの全テストを実行**

Run: `pytest tests/test_fetch_news.py -v`
Expected: 全てPASS

- [ ] **Step 13: コミット**

```bash
git add fetch_news.py tests/test_fetch_news.py
git commit -m "feat: load feed config and fetch individual RSS feeds"
```

---

### Task 3: 重複排除・ソート・オーケストレーション

**Files:**
- Modify: `fetch_news.py`
- Test: `tests/test_fetch_news.py`

**Interfaces:**
- Consumes: `fetch_feed(name, url) -> list[dict]`、`load_feeds(config_path) -> list[dict]`(Task 2)
- Produces:
  - `dedupe_articles(articles: list[dict]) -> list[dict]`
  - `sort_and_limit(articles: list[dict], per_source_limit: int = 10) -> list[dict]`
  - `get_all_articles(config_path: str, per_source_limit: int = 10) -> list[dict]`
  - Task 4の `generate_site.py` がこれらを消費する(特に `get_all_articles`)

- [ ] **Step 1: `dedupe_articles` の失敗するテストを書く**

```python
def _article(title, link, source="S1"):
    return {
        "title": title,
        "link": link,
        "source": source,
        "published_parsed": None,
        "published_display": "",
    }


def test_dedupe_articles_removes_duplicate_links_and_titles():
    articles = [
        _article("Same Title", "https://example.com/a/"),
        _article("Same Title", "https://example.com/a"),
        _article("Different Title", "https://example.com/a/"),
        _article("Unique", "https://example.com/b"),
    ]

    result = fetch_news.dedupe_articles(articles)

    assert [a["link"] for a in result] == [
        "https://example.com/a/",
        "https://example.com/b",
    ]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_dedupe_articles_removes_duplicate_links_and_titles -v`
Expected: FAIL(`AttributeError: module 'fetch_news' has no attribute 'dedupe_articles'`)

- [ ] **Step 3: `_normalize_link` と `dedupe_articles` を実装**

`fetch_news.py` に追記:

```python
def _normalize_link(link):
    if not link:
        return ""
    parts = urlsplit(link)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def dedupe_articles(articles):
    """Remove duplicates by normalized link OR exact title match, keeping
    the first occurrence encountered.
    """
    seen_links = set()
    seen_titles = set()
    result = []
    for article in articles:
        norm_link = _normalize_link(article["link"])
        title_key = article["title"].strip()
        if (norm_link and norm_link in seen_links) or (title_key in seen_titles):
            continue
        if norm_link:
            seen_links.add(norm_link)
        seen_titles.add(title_key)
        result.append(article)
    return result
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_fetch_news.py::test_dedupe_articles_removes_duplicate_links_and_titles -v`
Expected: PASS

- [ ] **Step 5: `sort_and_limit` の失敗するテストを書く**

```python
def test_sort_and_limit_per_source():
    def art(title, source, day):
        return {
            "title": title,
            "link": f"https://x/{title}",
            "source": source,
            "published_parsed": time.strptime(f"2026-09-{day:02d}", "%Y-%m-%d"),
            "published_display": "",
        }

    articles = [art(f"S1-{i}", "S1", i) for i in range(1, 5)] + [art("S2-1", "S2", 10)]

    result = fetch_news.sort_and_limit(articles, per_source_limit=2)

    s1_titles = [a["title"] for a in result if a["source"] == "S1"]
    assert s1_titles == ["S1-4", "S1-3"]
    assert result[0]["title"] == "S2-1"
```

(`time` と `feedparser` は Task 2 Step 1 でファイル冒頭にimport済み)

- [ ] **Step 6: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_sort_and_limit_per_source -v`
Expected: FAIL(`AttributeError: module 'fetch_news' has no attribute 'sort_and_limit'`)

- [ ] **Step 7: `sort_and_limit` を実装**

```python
def sort_and_limit(articles, per_source_limit=10):
    """Sort each source's articles newest-first and keep only the top
    `per_source_limit` per source. Articles without a parsed publish date
    sort last within their source. The final list is sorted newest-first
    overall.
    """
    by_source = {}
    for article in articles:
        by_source.setdefault(article["source"], []).append(article)

    limited = []
    for source_articles in by_source.values():
        source_articles.sort(
            key=lambda a: a["published_parsed"] or time.gmtime(0),
            reverse=True,
        )
        limited.extend(source_articles[:per_source_limit])

    limited.sort(key=lambda a: a["published_parsed"] or time.gmtime(0), reverse=True)
    return limited
```

- [ ] **Step 8: テストが通ることを確認**

Run: `pytest tests/test_fetch_news.py::test_sort_and_limit_per_source -v`
Expected: PASS

- [ ] **Step 9: `get_all_articles` の失敗するテストを書く**

```python
def test_get_all_articles_orchestrates(tmp_path, monkeypatch):
    feeds_path = tmp_path / "feeds.yaml"
    feeds_path.write_text(
        "- name: Source A\n  url: https://a.example.com/rss\n"
        "- name: Source B\n  url: https://b.example.com/rss\n",
        encoding="utf-8",
    )

    def fake_fetch_feed(name, url):
        if name == "Source A":
            day = "20"
        else:
            day = "21"
        return [
            {
                "title": f"{name} article",
                "link": f"https://x/{name}",
                "source": name,
                "published_parsed": time.strptime(f"2026-09-{day}", "%Y-%m-%d"),
                "published_display": "",
            }
        ]

    monkeypatch.setattr(fetch_news, "fetch_feed", fake_fetch_feed)

    articles = fetch_news.get_all_articles(str(feeds_path))

    assert [a["title"] for a in articles] == ["Source B article", "Source A article"]
```

- [ ] **Step 10: テストが失敗することを確認**

Run: `pytest tests/test_fetch_news.py::test_get_all_articles_orchestrates -v`
Expected: FAIL(`AttributeError: module 'fetch_news' has no attribute 'get_all_articles'`)

- [ ] **Step 11: `get_all_articles` を実装**

```python
def get_all_articles(config_path, per_source_limit=10):
    """Orchestrate load_feeds -> fetch_feed (per feed) -> dedupe_articles
    -> sort_and_limit. Returns the final article list, which may be empty
    if every feed failed.
    """
    feeds = load_feeds(config_path)
    all_articles = []
    for feed in feeds:
        all_articles.extend(fetch_feed(feed["name"], feed["url"]))
    deduped = dedupe_articles(all_articles)
    return sort_and_limit(deduped, per_source_limit)
```

- [ ] **Step 12: 全テストを実行**

Run: `pytest tests/test_fetch_news.py -v`
Expected: 全てPASS

- [ ] **Step 13: コミット**

```bash
git add fetch_news.py tests/test_fetch_news.py
git commit -m "feat: dedupe, sort/limit, and orchestrate feed fetching"
```

---

### Task 4: サイト生成(テンプレート・`generate_site.py`)

**Files:**
- Create: `templates/index.html.j2`
- Create: `generate_site.py`
- Test: `tests/test_generate_site.py`

**Interfaces:**
- Consumes: `fetch_news.get_all_articles(config_path, per_source_limit=10) -> list[dict]`(Task 3)。各記事dictは `title`, `link`, `source`, `published_display` キーを使う
- Produces: `render_html(articles, generated_at_display) -> str`、`write_site(html, output_path) -> None`、`main() -> None`(CLIエントリポイント、Task 5のワークフローが `python generate_site.py` として呼ぶ)

- [ ] **Step 1: `templates/index.html.j2` を作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIニュースまとめ</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 640px;
    margin: 0 auto;
    padding: 16px;
    background: #fafafa;
    color: #1a1a1a;
  }
  @media (prefers-color-scheme: dark) {
    body { background: #121212; color: #e6e6e6; }
    .card { background: #1e1e1e; }
  }
  h1 { font-size: 1.4rem; }
  .updated { color: #666; font-size: 0.85rem; margin-bottom: 16px; }
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }
  .source { font-size: 0.8rem; color: #1a73e8; font-weight: bold; }
  .title a { color: inherit; text-decoration: none; font-size: 1rem; }
  .title a:hover { text-decoration: underline; }
  .date { font-size: 0.75rem; color: #888; margin-top: 4px; }
</style>
</head>
<body>
  <h1>AIニュースまとめ</h1>
  <div class="updated">最終更新: {{ generated_at }}</div>
  {% for article in articles %}
  <div class="card">
    <div class="source">{{ article.source }}</div>
    <div class="title"><a href="{{ article.link }}" target="_blank" rel="noopener">{{ article.title }}</a></div>
    <div class="date">{{ article.published_display }}</div>
  </div>
  {% endfor %}
</body>
</html>
```

- [ ] **Step 2: `render_html` の失敗するテストを書く**

`tests/test_generate_site.py` を新規作成:

```python
import generate_site


def test_render_html_includes_articles():
    articles = [
        {
            "title": "Hello",
            "link": "https://x/1",
            "source": "S1",
            "published_display": "2026-09-21 00:00 UTC",
        }
    ]

    html = generate_site.render_html(articles, "2026-09-21 01:00 UTC")

    assert "Hello" in html
    assert "https://x/1" in html
    assert "S1" in html
    assert "2026-09-21 01:00 UTC" in html
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_includes_articles -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'generate_site'`)

- [ ] **Step 4: `generate_site.py` を作成し `render_html` を実装**

```python
import sys
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from fetch_news import get_all_articles

TEMPLATE_DIR = Path(__file__).parent / "templates"
FEEDS_CONFIG = Path(__file__).parent / "feeds.yaml"
OUTPUT_PATH = Path(__file__).parent / "docs" / "index.html"


def render_html(articles, generated_at_display):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("index.html.j2")
    return template.render(articles=articles, generated_at=generated_at_display)
```

- [ ] **Step 5: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_render_html_includes_articles -v`
Expected: PASS

- [ ] **Step 6: `write_site` の失敗するテストを書く**

```python
def test_write_site_creates_file(tmp_path):
    output_path = tmp_path / "docs" / "index.html"

    generate_site.write_site("<html></html>", output_path)

    assert output_path.read_text(encoding="utf-8") == "<html></html>"
```

- [ ] **Step 7: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_write_site_creates_file -v`
Expected: FAIL(`AttributeError: module 'generate_site' has no attribute 'write_site'`)

- [ ] **Step 8: `write_site` を実装**

`generate_site.py` に追記:

```python
def write_site(html, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
```

- [ ] **Step 9: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_write_site_creates_file -v`
Expected: PASS

- [ ] **Step 10: `main` の失敗するテストを書く(記事0件で異常終了するケース)**

```python
import pytest


def test_main_exits_when_no_articles(monkeypatch):
    monkeypatch.setattr(generate_site, "get_all_articles", lambda path: [])

    with pytest.raises(SystemExit) as exc_info:
        generate_site.main()

    assert exc_info.value.code == 1
```

- [ ] **Step 11: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_main_exits_when_no_articles -v`
Expected: FAIL(`AttributeError: module 'generate_site' has no attribute 'main'`)

- [ ] **Step 12: `main` を実装(記事0件の異常終了パスのみ、最小実装)**

`generate_site.py` に追記:

```python
def main():
    articles = get_all_articles(str(FEEDS_CONFIG))
    if not articles:
        print(
            "No articles fetched from any feed; leaving docs/index.html unchanged.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 13: テストが通ることを確認**

Run: `pytest tests/test_generate_site.py::test_main_exits_when_no_articles -v`
Expected: PASS

- [ ] **Step 14: `main` 成功ケースの失敗するテストを書く**

```python
def test_main_writes_site_on_success(monkeypatch, tmp_path):
    sample = [
        {
            "title": "T",
            "link": "https://x/1",
            "source": "S",
            "published_display": "d",
        }
    ]
    monkeypatch.setattr(generate_site, "get_all_articles", lambda path: sample)
    output_path = tmp_path / "index.html"
    monkeypatch.setattr(generate_site, "OUTPUT_PATH", output_path)

    generate_site.main()

    assert output_path.exists()
    assert "T" in output_path.read_text(encoding="utf-8")
```

- [ ] **Step 15: テストが失敗することを確認**

Run: `pytest tests/test_generate_site.py::test_main_writes_site_on_success -v`
Expected: FAIL(`assert output_path.exists()` で失敗する。Step 12の実装は記事がある場合に何も書き出さずそのまま関数を抜けるため)

- [ ] **Step 16: `main` に成功パス(HTML生成・書き出し)を追加**

`generate_site.py` の `main` を次のように書き換える:

```python
def main():
    articles = get_all_articles(str(FEEDS_CONFIG))
    if not articles:
        print(
            "No articles fetched from any feed; leaving docs/index.html unchanged.",
            file=sys.stderr,
        )
        sys.exit(1)

    generated_at_display = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    html = render_html(articles, generated_at_display)
    write_site(html, OUTPUT_PATH)
    print(f"Wrote {len(articles)} articles to {OUTPUT_PATH}")
```

Run: `pytest tests/test_generate_site.py -v`
Expected: 全てPASS

- [ ] **Step 17: コミット**

```bash
git add templates/index.html.j2 generate_site.py tests/test_generate_site.py
git commit -m "feat: render and write the AI news static site"
```

---

### Task 5: GitHub Actionsワークフロー

**Files:**
- Create: `.github/workflows/update-news.yml`
- Test: `tests/test_workflow_yaml.py`

**Interfaces:**
- Consumes: `requirements.txt`(Task 1)、`generate_site.py`(Task 4、`python generate_site.py` として実行)
- Produces: `docs/index.html` への日次コミット(Task 7でリポジトリがGitHubに存在することが前提)

- [ ] **Step 1: ワークフローYAMLが妥当であることを確認する失敗するテストを書く**

`tests/test_workflow_yaml.py` を新規作成:

```python
from pathlib import Path

import yaml


def test_workflow_yaml_is_valid_and_has_schedule_and_dispatch():
    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "update-news.yml"
    )

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = yaml.safe_load(f)

    # PyYAML(YAML 1.1)は `on:` を真偽値キー True としてパースするため両方を許容する
    on_section = workflow.get("on", workflow.get(True))
    assert on_section is not None
    assert on_section["schedule"][0]["cron"] == "0 22 * * *"
    assert "workflow_dispatch" in on_section
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_workflow_yaml.py -v`
Expected: FAIL(`FileNotFoundError`)

- [ ] **Step 3: `.github/workflows/update-news.yml` を作成**

```yaml
name: Update AI News

on:
  schedule:
    - cron: "0 22 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -r requirements.txt

      - run: python generate_site.py

      - name: Commit and push if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/index.html
          git diff --staged --quiet || git commit -m "Update AI news"
          git push
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_workflow_yaml.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add .github/workflows/update-news.yml tests/test_workflow_yaml.py
git commit -m "ci: add daily scheduled workflow to regenerate the news site"
```

---

### Task 6: ローカルでのエンドツーエンド確認(実データ)

**Files:**
- なし(コード変更なし。実データに対する動作確認)

**Interfaces:**
- Consumes: Task 1〜5で作成した全モジュール一式
- Produces: `docs/index.html`(実際のITmedia AI+ / AINOWの記事を含む、コミット対象)

- [ ] **Step 1: 全自動テストを実行し、既存の実装に問題がないことを確認**

Run: `pytest -v`
Expected: 全てPASS

- [ ] **Step 2: 実際のRSSフィードに対して `generate_site.py` を実行**

Run: `python generate_site.py`
Expected: `Wrote N articles to .../docs/index.html` が表示され、終了コード0

- [ ] **Step 3: 生成された `docs/index.html` を目視確認**

`docs/index.html` を開き、ITmedia AI+ と AINOW の記事タイトル・リンクが両方含まれていること、日付順に並んでいることを確認する。

- [ ] **Step 4: 意図的に1つのフィードURLを壊して部分失敗を確認**

`feeds.yaml` の1つの `url` を一時的に存在しないURL(例: `https://example.invalid/rss`)に書き換えて `python generate_site.py` を再実行し、正常なフィードの記事だけが表示され、エラーで異常終了しないことを確認する。確認後、`feeds.yaml` を元に戻す。

Run: `git diff feeds.yaml`
Expected: 差分なし(元に戻っていること)

- [ ] **Step 5: 生成された `docs/index.html` をコミット**

```bash
git add docs/index.html
git commit -m "chore: generate initial docs/index.html from live feeds"
```

---

### Task 7: GitHubリポジトリ作成・Pages公開・動作確認

> ⚠️ このタスクはパブリックなGitHubリポジトリの作成とプッシュを伴う、外部から見える/元に戻しにくい操作です。実行前に必ずユーザーに確認すること。GitHubアカウントへのログイン(`gh auth login`、ブラウザでの認証)はユーザー自身が行う必要がある。

**Files:**
- なし(GitHub上の設定操作)

**Interfaces:**
- Consumes: Task 1〜6で作成したリポジトリ一式
- Produces: 公開されたGitHub PagesのURL

- [ ] **Step 1: GitHubにログイン済みか確認**

Run: `gh auth status`
Expected: ログイン済みであれば続行。未ログインならユーザーに `gh auth login` の実行を依頼する(対話的ログインが必要なため代行不可)

- [ ] **Step 2: ユーザーにリポジトリ作成の実行可否を確認**

ユーザーに「GitHub上に `ai-news-app` という名前のパブリックリポジトリを作成してプッシュしてよいか」を確認する。承認を得てから次のステップに進む。

- [ ] **Step 3: リポジトリを作成しプッシュ**

```bash
gh repo create ai-news-app --public --source=. --remote=origin --push
```

Expected: リポジトリが作成され、現在のコミット履歴がプッシュされる

- [ ] **Step 4: GitHub Pagesを `main` ブランチの `/docs` フォルダに設定**

```bash
gh api repos/{owner}/ai-news-app/pages -X POST -f "source[branch]=main" -f "source[path]=/docs"
```

`{owner}` は `gh api user -q .login` で取得したユーザー名に置き換える。既にPages設定が存在してエラーになる場合はGitHubのリポジトリ設定画面(Settings → Pages)から手動設定する。

- [ ] **Step 5: ワークフローを手動トリガーして動作確認**

```bash
gh workflow run update-news.yml
```

数十秒待ってから:

```bash
gh run list --workflow=update-news.yml --limit 1
```

Expected: 直近の実行が `completed` / `success` であること

- [ ] **Step 6: 公開URLを取得しスマホで開いて確認**

```bash
gh api repos/{owner}/ai-news-app/pages -q .html_url
```

表示されたURLをスマホのブラウザで開き、レイアウト崩れがないこと、記事が表示されることを確認する。問題なければホーム画面に追加する。

- [ ] **Step 7: 完了報告**

ユーザーに公開URLを共有し、「毎朝UTC22時(JST7時)に自動更新される」ことを伝える。
