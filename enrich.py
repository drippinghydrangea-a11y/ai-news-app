import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT_SECONDS = 30
TOP_RECOMMENDED_COUNT = 10


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


def _parse_enrichment(text, expected_count):
    parsed = json.loads(text)
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        raise ValueError(
            f"Expected a JSON array of {expected_count} items, got: {parsed!r}"
        )
    for item in parsed:
        if not isinstance(item, dict) or not {"summary", "star", "recommended"} <= item.keys():
            raise ValueError(f"Malformed enrichment item: {item!r}")
        if not isinstance(item["summary"], str):
            raise ValueError(f"summary must be a string: {item!r}")
        if not isinstance(item["star"], int) or not (1 <= item["star"] <= 5):
            raise ValueError(f"star must be an int in 1..5: {item!r}")
    return parsed


def _call_gemini(prompt, api_key):
    response = requests.post(
        GEMINI_API_URL,
        headers={"x-goog-api-key": api_key},
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

    if not articles:
        return fallback

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback

    try:
        prompt = _build_prompt(articles)
        text = _call_gemini(prompt, api_key)
        enrichment = _parse_enrichment(text, len(articles))
    except Exception as exc:
        logger.warning("Gemini enrichment failed: %s", type(exc).__name__)
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
