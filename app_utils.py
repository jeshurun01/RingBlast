"""Pure helpers shared by the RingBlast Streamlit application and tests."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_upload_base(filename: str) -> str:
    """Return a traversal-free, archive-safe basename without its extension."""
    normalized = str(filename or "").replace("\\", "/")
    basename = os.path.basename(normalized)
    stem = os.path.splitext(basename)[0]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return safe or "upload"


def unique_upload_base(filename: str, used: set[str]) -> str:
    """Return a safe basename unique within ``used`` and reserve it."""
    root = safe_upload_base(filename)
    candidate = root
    suffix = 2
    while candidate in used:
        candidate = f"{root}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def upload_fingerprint(files: Iterable[tuple[str, bytes]]) -> tuple[tuple[str, str], ...]:
    """Fingerprint upload names and bytes so same-name revisions invalidate state."""
    return tuple(
        (os.path.basename(str(name).replace("\\", "/")), hashlib.sha256(data).hexdigest())
        for name, data in files
    )


def csv_safe_cell(value):
    """Prevent spreadsheet software from interpreting XML-controlled text as formulas."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
