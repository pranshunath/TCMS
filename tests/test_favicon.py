"""Tests verifying the presence of the inline SVG favicon."""
from pathlib import Path

BASE_HTML_PATH = Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"


def test_base_html_has_inline_svg_favicon():
    content = BASE_HTML_PATH.read_text(encoding="utf-8")
    assert 'rel="icon"' in content or "rel='icon'" in content
    assert 'type="image/svg+xml"' in content or "type='image/svg+xml'" in content
    assert 'href="data:image/svg+xml' in content or "href='data:image/svg+xml" in content
