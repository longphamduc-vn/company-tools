"""Data models for Outlook Rule Companion."""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


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

