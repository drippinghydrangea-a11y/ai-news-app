import logging
import socket
import time
from urllib.parse import urlsplit, urlunsplit

import feedparser
import yaml

logger = logging.getLogger(__name__)

socket.setdefaulttimeout(20)


def load_feeds(config_path):
    """Load feed definitions from a YAML file.

    Returns a list of dicts: {"name": str, "url": str}
    """
    with open(config_path, "r", encoding="utf-8") as f:
        feeds = yaml.safe_load(f)
    return feeds or []


def fetch_feed(name, url):
    """Fetch and parse a single RSS feed.

    Returns a list of article dicts on success, or an empty list if the
    feed could not be fetched/parsed (a warning is logged in that case).
    """
    try:
        parsed = feedparser.parse(url)
    except Exception as exc:
        logger.warning("Failed to fetch feed %s (%s): %s", name, url, exc)
        return []

    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Failed to fetch feed %s (%s): %s",
            name, url, parsed.get("bozo_exception"),
        )
        return []

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
