import pytest

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


def test_render_html_escapes_untrusted_content():
    articles = [
        {
            "title": "<script>alert(1)</script>",
            "link": "https://x/1",
            "source": "S1",
            "published_display": "2026-09-21 00:00 UTC",
        }
    ]

    html = generate_site.render_html(articles, "2026-09-21 01:00 UTC")

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_write_site_creates_file(tmp_path):
    output_path = tmp_path / "docs" / "index.html"

    generate_site.write_site("<html></html>", output_path)

    assert output_path.read_text(encoding="utf-8") == "<html></html>"


def test_main_exits_when_no_articles(monkeypatch):
    monkeypatch.setattr(generate_site, "get_all_articles", lambda path: [])

    with pytest.raises(SystemExit) as exc_info:
        generate_site.main()

    assert exc_info.value.code == 1


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
