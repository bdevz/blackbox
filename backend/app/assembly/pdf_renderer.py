"""Convert assembled markdown proposal to PDF via WeasyPrint."""

import os


STYLES_PATH = os.path.join(os.path.dirname(__file__), "styles.css")


def markdown_to_html(markdown_text: str, title: str = "Proposal") -> str:
    """Convert markdown to styled HTML document."""
    try:
        import markdown as md
        body = md.markdown(markdown_text, extensions=["tables", "toc", "fenced_code"])
    except ImportError:
        import re
        body = markdown_text
        body = re.sub(r"^### (.+)$", r"<h3>\1</h3>", body, flags=re.MULTILINE)
        body = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=re.MULTILINE)
        body = re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=re.MULTILINE)
        body = body.replace("\n\n", "</p><p>")
        body = f"<p>{body}</p>"

    css = ""
    if os.path.exists(STYLES_PATH):
        with open(STYLES_PATH) as f:
            css = f.read()

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>"""


def render_pdf(markdown_text: str, title: str = "Proposal") -> bytes:
    """Render markdown proposal to PDF bytes."""
    from weasyprint import HTML
    html_content = markdown_to_html(markdown_text, title)
    return HTML(string=html_content).write_pdf()
