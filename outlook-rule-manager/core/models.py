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

