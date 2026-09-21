import sys
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from fetch_news import get_all_articles

TEMPLATE_DIR = Path(__file__).parent / "templates"
FEEDS_CONFIG = Path(__file__).parent / "feeds.yaml"
OUTPUT_PATH = Path(__file__).parent / "docs" / "index.html"


def render_html(articles, generated_at_display):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html.j2")
    return template.render(articles=articles, generated_at=generated_at_display)


def write_site(html, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


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


if __name__ == "__main__":
    main()
