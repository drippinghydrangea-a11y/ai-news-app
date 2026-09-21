import json

import requests

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT_SECONDS = 30


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
    return parsed


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
