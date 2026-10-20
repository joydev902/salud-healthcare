import re

_WS = re.compile(r"\s+")


def clean(value: str | None) -> str | None:
    """Trim and collapse internal whitespace; empty strings become None."""
    if value is None:
        return None
    value = _WS.sub(" ", value).strip()
    return value or None


def normalize_name(value: str) -> str:
    """Matching key for payer/provider/group names: whitespace-collapsed, case-folded."""
    return _WS.sub(" ", value).strip().casefold()


def like_escape(term: str) -> str:
    """Escape LIKE wildcards so user search text matches literally (use escape='\\')."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_code(value: str | None) -> str | None:
    """ICD-10 / HCC codes: uppercase, no dots or spaces (I25.10 -> I2510)."""
    if value is None:
        return None
    value = value.replace(".", "").replace(" ", "").strip().upper()
    return value or None
