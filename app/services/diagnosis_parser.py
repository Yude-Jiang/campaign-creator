"""Parse uploaded GEO diagnosis files (Markdown / HTML).

Extracts raw text content for downstream LLM analysis.
The deep structured extraction (gap_type, competitors, recall strength)
is done by the LLM in plan_service via the analyze_diagnosis prompt.
"""

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_diagnosis_file(filepath: str | Path) -> str:
    """Read a diagnosis file and extract its raw text content.

    Supports .md (plain text) and .html files.
    Returns the full text content suitable for LLM consumption.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("Diagnosis file not found: %s", path)
        return ""

    suffix = path.suffix.lower()

    if suffix in (".md", ".markdown", ".txt"):
        return _parse_markdown(path)
    elif suffix in (".html", ".htm"):
        return _parse_html(path)
    else:
        # Try as plain text
        logger.warning("Unknown file type: %s, reading as plain text", suffix)
        return path.read_text(encoding="utf-8", errors="replace")


def _parse_markdown(path: Path) -> str:
    """Read markdown file as-is (the LLM can parse markdown natively)."""
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return ""
    return content


def _parse_html(path: Path) -> str:
    """Extract readable text from an HTML diagnosis file."""
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        soup = BeautifulSoup(content, "html.parser")
        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        # Get text, preserving some structure
        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    except Exception as e:
        logger.warning("BeautifulSoup parsing failed: %s, falling back to raw text", e)
        # Return cleaned HTML as fallback
        return re.sub(r"<[^>]+>", " ", content)


def parse_diagnoses_for_campaign(
    campaign_data: dict,
    data_dir: str = "data",
) -> list[dict]:
    """Load all diagnosis files for a campaign and return as question_id → raw_text.

    Returns a list of dicts: [{"question_id": "q1", "raw_text": "...", "filename": "..."}, ...]
    """
    campaign_id = campaign_data.get("campaign_id", "")
    if not campaign_id:
        return []

    diagnoses_dir = Path(data_dir) / "campaigns" / campaign_id / "diagnoses"
    if not diagnoses_dir.exists():
        return []

    results = []
    for diag_entry in campaign_data.get("diagnoses", []):
        question_id = diag_entry.get("question_id", "")
        filename = diag_entry.get("filename", "")
        if not filename:
            # Try to find file by question_id pattern
            for f in diagnoses_dir.iterdir():
                if f.stem.startswith(question_id):
                    filename = f.name
                    break

        if filename:
            filepath = diagnoses_dir / filename
            if filepath.exists():
                raw_text = parse_diagnosis_file(filepath)
                results.append({
                    "question_id": question_id,
                    "filename": filename,
                    "raw_text": raw_text,
                })
            else:
                logger.warning("Diagnosis file referenced but not found: %s", filepath)
                results.append({
                    "question_id": question_id,
                    "filename": filename,
                    "raw_text": "",
                })

    return results
