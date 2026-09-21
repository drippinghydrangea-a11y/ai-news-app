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


def test_render_html_includes_pwa_head_links_and_timestamp():
    articles = [
        {
            "title": "T", "link": "https://x/1", "source": "S", "published_display": "d",
            "published_iso": "2026-09-21T00:00:00Z",
            "summary": None, "star": None, "recommended": False,
        }
    ]

    html = generate_site.render_html(articles, "now")

    assert 'rel="manifest"' in html
    assert 'rel="apple-touch-icon"' in html
    assert 'data-timestamp="2026-09-21T00:00:00Z"' in html
