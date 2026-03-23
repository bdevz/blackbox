"""RFP document parser — extracts text from PDF/DOCX, parses into structured brief."""

import io
import json
import logging
import re

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

BRIEF_SCHEMA = {
    "title": "str — RFP title",
    "agency": "str — issuing agency name",
    "state": "str — US state",
    "category": "str — RFP category (e.g. IT Consulting)",
    "deadline": "str — submission deadline (YYYY-MM-DD)",
    "estimated_value": "float or null — estimated contract value in USD",
    "requirements": "list[str] — mandatory requirements",
    "scope": "str — scope of work description",
    "evaluation_criteria": "dict[str, int] — criteria name to weight",
}


def extract_text(content: bytes, filename: str) -> str:
    """Extract plain text from PDF, DOCX, or text file."""
    if not content:
        raise ValueError("Document content is empty")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()

    elif ext == "docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs)
        return text.strip()

    elif ext in ("txt", "text", "md"):
        return content.decode("utf-8", errors="replace").strip()

    else:
        raise ValueError(f"Unsupported file format: .{ext}")


def validate_brief(brief: dict) -> dict:
    """Validate that parsed brief has minimum required fields."""
    required = ["title", "agency"]
    for field in required:
        if field not in brief or not brief[field]:
            raise ValueError(f"Parsed brief missing required field: {field}")

    brief.setdefault("state", "")
    brief.setdefault("category", "")
    brief.setdefault("deadline", None)
    brief.setdefault("estimated_value", None)
    brief.setdefault("requirements", [])
    brief.setdefault("scope", "")
    brief.setdefault("evaluation_criteria", {})

    return brief


async def parse_brief(text: str) -> dict:
    """Use Claude Haiku to parse raw document text into a structured brief."""
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = """You are an RFP document parser. Extract structured data from raw RFP document text.

Respond with ONLY valid JSON (no markdown fences):
{
  "title": "RFP title",
  "agency": "issuing agency name",
  "state": "US state (2-letter or full name)",
  "category": "category like IT Consulting, Construction, etc.",
  "deadline": "YYYY-MM-DD or null if not found",
  "estimated_value": 2500000.0 or null if not found,
  "requirements": ["requirement 1", "requirement 2"],
  "scope": "full scope of work description",
  "evaluation_criteria": {"criteria_name": weight_int}
}

Extract ONLY what is explicitly stated in the document. Do NOT infer or fabricate data.
If a field is not present in the document, use null or empty list/object."""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": f"Parse this RFP document:\n\n{text[:50000]}"}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, count=1)
    raw = re.sub(r"\n?```\s*$", "", raw)

    brief = json.loads(raw)
    return validate_brief(brief)
