"""
Data models for LGD Drawing Vault Batch Downloader & Viewer.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class DrawingItem:
    """Represents a drawing item to search and download."""
    qcode: str
    custom_name: str = ""

    def __post_init__(self):
        self.qcode = (self.qcode or "").strip().upper()
        self.custom_name = (self.custom_name or "").strip()


@dataclass
class DownloadResult:
    """Result of searching and downloading a drawing."""
    qcode: str
    custom_name: str = ""
    status: str = "Pending"  # "Success", "Failed: Drawing Not Found", "Failed: ...", etc.
    file_name: str = ""
    local_path: str = ""
    file_size_bytes: int = 0
    image_width: int = 0
    image_height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchDownloadSummary:
    """Summary of a batch download run."""
    total_requested: int = 0
    total_downloaded: int = 0
    total_failed: int = 0
    results: List[DownloadResult] = field(default_factory=list)
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requested": self.total_requested,
            "total_downloaded": self.total_downloaded,
            "total_failed": self.total_failed,
            "results": [r.to_dict() if isinstance(r, DownloadResult) else r for r in self.results],
            "error_message": self.error_message,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass
class DrawingRecord:
    """Internal representation of drawing metadata parsed from FDM search."""
    qcode: str
    drawing_oid: str
    fab_oid: str = "29113"
    folder_path: str = ""
    type_name: str = "Non-CAD"  # "CAD", "Non-CAD", "JPG", etc.
    file_name: str = ""
    doc_number: str = ""
    version: str = "latest"
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_cad(self) -> bool:
        """Skip records where typeName == 'CAD' (3D heavy vector formats)."""
        t = (self.type_name or "").strip().upper()
        return t == "CAD"
