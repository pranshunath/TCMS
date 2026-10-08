"""Tests ensuring template compliance, compilation, and helper rules."""
from pathlib import Path
import jinja2

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"


def test_all_templates_compile_cleanly():
    loader = jinja2.FileSystemLoader(str(TEMPLATES_DIR))
    env = jinja2.Environment(loader=loader)

    template_files = list(TEMPLATES_DIR.rglob("*.html"))
    assert len(template_files) >= 4, f"Found only {len(template_files)} templates"

    for tf in template_files:
        rel_name = str(tf.relative_to(TEMPLATES_DIR)).replace("\\", "/")
        # Compiling template
        template = env.get_template(rel_name)
        assert template is not None


def test_templates_extend_base_and_do_not_redefine_helpers():
    template_files = list(TEMPLATES_DIR.rglob("*.html"))

    for tf in template_files:
        rel_name = str(tf.relative_to(TEMPLATES_DIR)).replace("\\", "/")
        content = tf.read_text(encoding="utf-8")

        if rel_name != "base.html":
            # Must extend base.html
            assert '{% extends "base.html" %}' in content or "{% extends 'base.html' %}" in content, (
                f"{rel_name} does not extend base.html"
            )

            # Must NOT redefine esc or formatDate in sub-templates
            assert "function esc(" not in content, f"{rel_name} redefines esc() function"
            assert "function formatDate(" not in content, f"{rel_name} redefines formatDate() function"


def test_base_template_defines_standard_helpers():
    base_file = TEMPLATES_DIR / "base.html"
    content = base_file.read_text(encoding="utf-8")

    assert "function esc(" in content
    assert "function formatDate(" in content
