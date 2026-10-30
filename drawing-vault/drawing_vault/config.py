"""
Configuration constants and settings for Drawing Vault Automation.
"""

import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_FILE = str(PROJECT_ROOT / "session.json")
DEFAULT_DOWNLOAD_DIR = str(PROJECT_ROOT / "downloaded_images")

def _load_env_file() -> None:
    """Loads key-value pairs from .env file into os.environ if present."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.is_file():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()

# SSO Authentication Config
SSO_WS_HOST = os.getenv("VAULT_SSO_WS_HOST", "127.0.0.1")
SSO_WS_PORT = int(os.getenv("VAULT_SSO_WS_PORT", "28083"))
SSO_WS_URL = f"ws://{SSO_WS_HOST}:{SSO_WS_PORT}/"
SSO_WS_PAYLOAD = os.getenv(
    "VAULT_SSO_WS_PAYLOAD",
    "API?args=tsso://im.internal.net:8088/GETTOKEN?apiroot=/pdadmin&protocol=http&pd_h=null&pd_id=null",
)

# Token Exchange EAI Endpoint
SSO_TOKEN_EXCHANGE_URL = os.getenv(
    "VAULT_SSO_TOKEN_EXCHANGE_URL", "http://im.internal.net:8088/pdadmin/eai/eai.jsp"
)

# FDM Vault Endpoints
FDM_BASE_URL = os.getenv("VAULT_FDM_BASE_URL", "http://fdm.internal.net:8008")
FDM_SEARCH_URL = os.getenv("VAULT_FDM_SEARCH_URL", f"{FDM_BASE_URL}/")
FDM_DETAIL_NONCAD_PATH = os.getenv(
    "VAULT_FDM_DETAIL_NONCAD_PATH", "/Windchill/extcore/jsp/vault/drawing/detailNonCAD.jsp"
)
FDM_DETAIL_NONCAD_URL = f"{FDM_BASE_URL}{FDM_DETAIL_NONCAD_PATH}"

# Search Default Payload
DEFAULT_SITE = os.getenv("VAULT_SITE", "SP")
DEFAULT_FAB = os.getenv("VAULT_FAB", "29113")
DEFAULT_VERSION = "latest"
DEFAULT_PAGE_START = "1"
DEFAULT_PAGE_END = "500"

# Session Settings
SESSION_TTL_SECONDS = int(os.getenv("VAULT_SESSION_TTL", "7200"))  # 2 hours
REQUIRED_COOKIES = ["PD-TH-SESSION-ID", "PD-ID", "JSESSIONID"]

# Network Request Settings
DEFAULT_TIMEOUT_CONNECT = 10
DEFAULT_TIMEOUT_READ = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Supported Visual Raster Image Extensions
RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
