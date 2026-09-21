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
    real_parse = feedparser.parse

    def fake_parse(url):
        return real_parse(SAMPLE_RSS)

    monkeypatch.setattr(fetch_news.feedparser, "parse", fake_parse)

    articles = fetch_news.fetch_feed("Sample Source", "https://example.com/rss")

    assert len(articles) == 2
    assert articles[0]["title"] == "Article One"
    assert articles[0]["link"] == "https://example.com/one"
    assert articles[0]["source"] == "Sample Source"
    assert articles[0]["published_display"] == "2026-09-21 00:00 UTC"
    assert articles[1]["published_display"] == "2026-09-20 00:00 UTC"


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
