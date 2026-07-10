"""File-based persistence for campaign data."""

import json
import logging
import re
import threading
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Per-campaign locks for serializing concurrent read-modify-write cycles.
# FastAPI runs sync endpoints in a threadpool and async endpoints on the event
# loop, so we use threading.Lock (works for both, and the lock is held only
# for the brief file-I/O window, never across an await).
_campaign_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()  # protects _campaign_locks itself


@contextmanager
def campaign_lock(campaign_id: str):
    """Context manager that acquires the per-campaign write lock.

    Wrap any read-modify-write cycle with this to prevent two concurrent
    requests from reading the same state and having the second write
    silently overwrite the first.

    Usage:
        with campaign_lock(campaign_id):
            data = load_campaign_json(campaign_id)
            data["something"] = new_value
            save_campaign_json(campaign_id, data)
    """
    with _locks_guard:
        if campaign_id not in _campaign_locks:
            _campaign_locks[campaign_id] = threading.Lock()
        lock = _campaign_locks[campaign_id]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()

CAMPAIGNS_DIR = Path(settings.data_dir) / "campaigns"

# Safe characters for campaign IDs: alphanumeric, hyphens, underscores,
# and CJK Unified Ideographs (U+4E00–U+9FFF). Matches what _slugify produces.
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-一-鿿]+$")
_MAX_ID_LENGTH = 128


def validate_campaign_id(campaign_id: str) -> str:
    """Validate that a campaign_id is safe for filesystem use.

    Returns the validated ID unchanged if valid.
    Raises ValueError if the ID contains path traversal or unsafe characters.
    """
    if not campaign_id:
        raise ValueError("campaign_id must not be empty")
    if len(campaign_id) > _MAX_ID_LENGTH:
        raise ValueError(f"campaign_id too long (max {_MAX_ID_LENGTH} chars)")
    if ".." in campaign_id:
        raise ValueError("campaign_id must not contain '..'")
    if "/" in campaign_id or "\\" in campaign_id:
        raise ValueError("campaign_id must not contain path separators")
    if "\x00" in campaign_id:
        raise ValueError("campaign_id must not contain null bytes")
    if not _SAFE_ID_RE.match(campaign_id):
        raise ValueError(
            "campaign_id contains unsafe characters. "
            "Allowed: a-z, A-Z, 0-9, underscore, hyphen, CJK characters."
        )

    # Verify the resolved path stays within CAMPAIGNS_DIR
    resolved = (CAMPAIGNS_DIR / campaign_id).resolve()
    if not str(resolved).startswith(str(CAMPAIGNS_DIR.resolve())):
        raise ValueError("campaign_id resolves outside the data directory")

    return campaign_id


def ensure_campaign_dir(campaign_id: str) -> Path:
    """Ensure the campaign directory exists and return its path."""
    validate_campaign_id(campaign_id)
    path = CAMPAIGNS_DIR / campaign_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "diagnoses").mkdir(exist_ok=True)
    return path


def save_campaign_json(campaign_id: str, data: dict) -> Path:
    """Save campaign data as JSON (atomic write via temp file + rename)."""
    validate_campaign_id(campaign_id)
    path = ensure_campaign_dir(campaign_id) / "campaign.json"
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    # Atomic replace on the same filesystem — no window for a truncated file
    tmp_path.replace(path)
    logger.info("Saved campaign: %s", path)
    return path


def load_campaign_json(campaign_id: str) -> dict | None:
    """Load campaign data from JSON."""
    validate_campaign_id(campaign_id)
    path = CAMPAIGNS_DIR / campaign_id / "campaign.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_campaigns() -> list[dict]:
    """List all saved campaigns."""
    result = []
    if not CAMPAIGNS_DIR.exists():
        return result
    for d in sorted(CAMPAIGNS_DIR.iterdir(), reverse=True):
        if d.is_dir():
            json_path = d / "campaign.json"
            if json_path.exists():
                data = json.loads(json_path.read_text(encoding="utf-8"))
                result.append({
                    "campaign_id": d.name,
                    "name": (data.get("brief") or {}).get("name", d.name),
                    "updated_at": data.get("updated_at", ""),
                })
    return result


def save_diagnosis_file(campaign_id: str, question_id: str, content: bytes, filename: str) -> Path:
    """Save an uploaded GEO diagnosis file."""
    validate_campaign_id(campaign_id)
    # Also validate question_id to prevent path traversal in filenames
    safe_qid = re.sub(r"[^a-zA-Z0-9_\-]", "_", question_id)
    diag_dir = ensure_campaign_dir(campaign_id) / "diagnoses"
    ext = Path(filename).suffix
    if ext not in (".md", ".html", ".htm", ".txt"):
        raise ValueError(f"Unsupported file type: {ext}")
    save_path = diag_dir / f"{safe_qid}{ext}"
    save_path.write_bytes(content)
    logger.info("Saved diagnosis: %s", save_path)
    return save_path


def read_diagnosis_file(campaign_id: str, filename: str) -> str | None:
    """Read a diagnosis file's content."""
    validate_campaign_id(campaign_id)
    # Prevent path traversal in filename
    safe_filename = Path(filename).name  # strips any directory components
    path = CAMPAIGNS_DIR / campaign_id / "diagnoses" / safe_filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
