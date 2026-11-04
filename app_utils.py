"""Pure helpers shared by the RingBlast Streamlit application and tests."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_DEFAULT_COMBINED_REPORT = "combined_blast_reports.pdf"
DEFAULT_BATCH_LABEL = "RingBlast_Batch"

# Trailing ring marker of a batch input file / plan id: "..._R3", "... R10", "...-R2".
_RING_SUFFIX_RE = re.compile(r"[\s._-]*(?:SLOT|R)\s*\d+$", re.IGNORECASE)


def combined_report_filename(name: str | None) -> str:
    """Return a safe PDF filename for a combined report download/archive entry."""
    raw = str(name or "").strip()
    if raw.lower().endswith(".pdf"):
        raw = raw[:-4]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")[:120].rstrip("._-")
    return f"{safe}.pdf" if safe else _DEFAULT_COMBINED_REPORT


def stope_label_from_name(name: str | None) -> str:
    """Return a filesystem-safe stope/batch label for one input name.

    ``B27_S8_R1`` -> ``B27_S8``; ``B27 S8_R1`` -> ``B27_S8``; ``R7`` -> ``""``
    (a bare ring marker carries no stope information).
    """
    raw = str(name or "").strip().replace("\\", "/")
    stem = os.path.splitext(os.path.basename(raw))[0]
    stem = _RING_SUFFIX_RE.sub("", stem)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:120].strip("._-")


def batch_stope_label(names: Iterable[str],
                      fallback: str = DEFAULT_BATCH_LABEL) -> str:
    """Derive ONE stope/batch label from every input name in a batch.

    Names that reduce to the same label (the normal ``<STOPE>_R<n>`` case) win
    outright; otherwise the shared prefix is used, and ``fallback`` when the
    names share nothing usable.
    """
    labels = [label for label in (stope_label_from_name(n) for n in names) if label]
    if not labels:
        return fallback
    if len(set(labels)) == 1:
        return labels[0]
    prefix = os.path.commonprefix(labels).strip("._-")
    return prefix or fallback


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


def selected_plan_data(parsed_data: dict, selected_names: Iterable[str]) -> dict:
    """Return selected parsed plans in their original upload order."""
    selected = set(selected_names)
    return {name: data for name, data in parsed_data.items() if name in selected}


def csv_safe_cell(value):
    """Prevent spreadsheet software from interpreting XML-controlled text as formulas."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
