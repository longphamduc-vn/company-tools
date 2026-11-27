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


def validate_new_pst_path(path: str) -> str:
    """Return '' if a brand-new PST may be created at `path`, otherwise the reason it may not."""
    import os

    raw = (path or "").strip()
    if not raw:
        return "Choose where to save the new PST file."
    if not raw.lower().endswith(".pst"):
        return "The file name must end with .pst."
    low = raw.lower()
    if low.startswith("\\\\") or low.startswith("//") or "onedrive" in low or "sharepoint" in low:
        return "Do not keep PST files on OneDrive, SharePoint or a network share (they get corrupted). Pick a local drive."
    if os.path.exists(raw):
        return f"A file already exists there: {raw}. Pick a new name (nothing is overwritten)."
    folder = os.path.dirname(os.path.abspath(raw))
    if not os.path.isdir(folder):
        return f"The folder does not exist: {folder}"
    return ""


def suggest_new_pst(stores, year: int, default_dir: str = "") -> Tuple[str, str]:
    """Suggest (display name, file path) for a new yearly PST: 'Archive <year>' next to the open data files."""
    import os

    paths = [s.get("file_path", "") for s in (stores or []) if s.get("file_path")]
    folder = os.path.dirname(paths[0]) if paths else (
        default_dir or os.path.join(os.path.expanduser("~"), "Documents", "Outlook Files")
    )
    taken = {p.lower() for p in paths}
    n = 1
    while True:
        suffix = "" if n == 1 else f"_{n}"
        candidate = os.path.join(folder, f"Archive_{year}{suffix}.pst")
        if candidate.lower() not in taken and not os.path.exists(candidate):
            name = f"Archive {year}" if n == 1 else f"Archive {year} ({n})"
            return name, candidate
        n += 1
