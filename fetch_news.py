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
