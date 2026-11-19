"""Small text helpers shared by the scanner, the flow projection and the index."""

import re
import unicodedata
from datetime import datetime, timezone


D_SPECIAL = {"đ": "d", "Đ": "D"}


def strip_diacritics(text):
    """Fold Vietnamese text: tone marks AND the letter đ/Đ (not a combining mark)."""
    mapped = "".join(D_SPECIAL.get(ch, ch) for ch in str(text))
    decomposed = unicodedata.normalize("NFD", mapped)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_text(text):
    """Fold Vietnamese/English text to a comparable lowercase form."""
    return re.sub(r"\s+", " ", strip_diacritics(str(text)).lower()).strip()


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_text(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def clamp(text, limit=160):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
