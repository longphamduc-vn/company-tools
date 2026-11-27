"""Data models for Outlook Rule Companion."""
import re
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

MANAGED_PREFIX = "[Companion] "
_COMPILED_SUFFIX_RE = re.compile(r"(?:\s+\((?:Part \d+|Domains|Keywords)\))+$")


def extract_base_rule_name(rule_name: str) -> str:
    """Strip MANAGED_PREFIX and compiled sub-rule suffixes from an Outlook rule name."""
    name = rule_name or ""
    if name.startswith(MANAGED_PREFIX):
        name = name[len(MANAGED_PREFIX):]
    return _COMPILED_SUFFIX_RE.sub("", name)


def rule_name_from_folder(path: str) -> str:
    """Automatic rule name for a folder: its path joined with '_' (A\\B\\C -> A_B_C).

    In Outlook the rule is named MANAGED_PREFIX + this name ("[Companion] A_B_C"), which
    keeps it apart from rules the user created by hand.
    """
    return "_".join(s.strip() for s in re.split(r"[\\/]", path or "") if s.strip())


def outlook_rule_name(rule_name: str) -> str:
    """The name the rule gets in Outlook."""
    return f"{MANAGED_PREFIX}{rule_name}"


def pluralize_count(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Format an integer count with singular/plural unit (e.g. '1 sender', '2 senders')."""
    unit = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {unit}"


@dataclass
class StoreConfig:
    id: str
    name: str
    file_path: str
    store_id: str = ""


@dataclass
class AddressGroup:
    id: str
    name: str
    domains: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)


@dataclass
class RuleConfig:
    id: str
    name: str
    enabled: bool = True
    groups: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    subject_keywords: List[str] = field(default_factory=list)
    target_store: str = "active_archive"
    target_folder: str = ""
    # Names the rule had before automatic naming; still used to recognise the user's old
    # (unprefixed) Outlook rules of the same name as legacy copies.
    former_names: List[str] = field(default_factory=list)

    def known_names(self) -> List[str]:
        return [self.name] + [n for n in self.former_names if n and n != self.name]


@dataclass
class EmailMessage:
    entry_id: str
    subject: str
    sender_name: str
    sender_email: str
    received_time: datetime
    body: str = ""
    has_attachments: bool = False
    is_read: bool = False

