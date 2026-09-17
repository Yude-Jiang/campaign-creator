"""HTTP helpers."""

from __future__ import annotations

import re
from urllib.parse import quote

# RFC 5987 attr-char: keep these unescaped in filename* so extensions stay readable.
_ATTR_CHAR_SAFE = "!#$&+-.^_`|~"
_ASCII_FALLBACK_RE = re.compile(r"[^A-Za-z0-9.]+")


def content_disposition_attachment(filename: str) -> dict[str, str]:
    """Build a latin-1-safe Content-Disposition header (RFC 5987 / RFC 6266).

    Starlette encodes response headers as latin-1. Campaign IDs may contain CJK
    (``_slugify`` keeps U+4E00–U+9FFF), so interpolating them into
    ``filename={campaign_id}_personas.md`` raises UnicodeEncodeError and FastAPI
    returns ``{"detail": "'latin-1' codec can't encode characters..."}.``

    ASCII names keep the historical unquoted ``filename=`` form. Non-ASCII names
    use an ASCII ``filename`` fallback plus ``filename*=utf-8''…``.
    """
    try:
        filename.encode("ascii")
    except UnicodeEncodeError:
        encoded = quote(filename, safe=_ATTR_CHAR_SAFE)
        fallback = _ASCII_FALLBACK_RE.sub("-", filename)
        fallback = re.sub(r"-{2,}", "-", fallback).strip("-") or "download"
        if "." in filename:
            ext = filename[filename.rfind(".") :]
            if ext.isascii() and not fallback.endswith(ext):
                fallback = f"{fallback}{ext}"
        value = f"attachment; filename={fallback}; filename*=utf-8''{encoded}"
    else:
        value = f"attachment; filename={filename}"
    return {"Content-Disposition": value}
