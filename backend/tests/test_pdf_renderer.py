import pytest
from app.assembly.pdf_renderer import markdown_to_html


class TestMarkdownToHtml:
    def test_produces_html(self):
        html = markdown_to_html("# Hello\n\nWorld", title="Test")
        assert "<html>" in html
        assert "<title>Test</title>" in html

    def test_includes_css(self):
        html = markdown_to_html("# Test")
        assert "<style>" in html
        assert "font-family" in html

    def test_converts_headers(self):
        html = markdown_to_html("# Section One\n\n## Sub Section")
        assert "Section One" in html

    def test_converts_tables(self):
        md = "| Col1 | Col2 |\n|------|------|\n| A | B |"
        html = markdown_to_html(md)
        assert "Col1" in html


class TestRenderPdf:
    def test_produces_pdf_bytes(self):
        try:
            from app.assembly.pdf_renderer import render_pdf
            pdf = render_pdf("# Test Proposal\n\nContent here.")
            assert pdf[:4] == b"%PDF"
            assert len(pdf) > 100
        except ImportError:
            pytest.skip("weasyprint not installed")
