"""Pure helpers for suggesting next-year PST archive names and file paths."""
import re
from typing import Tuple

_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def _increment_year_in_text(text: str) -> str:
    """Increment the last standalone 4-digit year in text, or return '' if none."""
    matches = list(_YEAR_RE.finditer(text or ""))
    if not matches:
        return ""
    last = matches[-1]
    next_year = str(int(last.group(1)) + 1)
    return f"{text[:last.start()]}{next_year}{text[last.end():]}"


def suggest_rollover_target(current_name: str, current_path: str) -> Tuple[str, str]:
    """Suggest next-year (store_name, pst_file_path) from current archive metadata.

    Increments the 4-digit year in current_name and in the filename segment of
    current_path (preserving the directory and separator). Returns '' for either
    field that does not contain a 4-digit year.
    """
    suggested_name = _increment_year_in_text((current_name or "").strip())

    raw_path = (current_path or "").strip()
    suggested_path = ""
    if raw_path:
        sep_idx = max(raw_path.rfind("\\"), raw_path.rfind("/"))
        dir_prefix = raw_path[: sep_idx + 1] if sep_idx >= 0 else ""
        file_name = raw_path[sep_idx + 1 :] if sep_idx >= 0 else raw_path
        next_file = _increment_year_in_text(file_name)
        if next_file:
            suggested_path = f"{dir_prefix}{next_file}"

    return suggested_name, suggested_path
