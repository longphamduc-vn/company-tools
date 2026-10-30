"""
Configuration constants and settings for LGD Drawing Vault Automation.
"""

import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_FILE = str(PROJECT_ROOT / "session.json")
DEFAULT_DOWNLOAD_DIR = str(PROJECT_ROOT / "downloaded_images")

# SSO Authentication Config
SSO_WS_HOST = os.getenv("LGD_SSO_WS_HOST", "127.0.0.1")
SSO_WS_PORT = int(os.getenv("LGD_SSO_WS_PORT", "28083"))
SSO_WS_URL = f"ws://{SSO_WS_HOST}:{SSO_WS_PORT}/"
SSO_WS_PAYLOAD = "API?args=tsso://im.lgdisplay.com:8088/GETTOKEN?apiroot=/pdadmin&protocol=http&pd_h=null&pd_id=null"

# Token Exchange EAI Endpoint
SSO_TOKEN_EXCHANGE_URL = os.getenv(
    "LGD_SSO_TOKEN_EXCHANGE_URL",
    "http://im.lgdisplay.com:8088/pdadmin/eai/eai.jsp"
)

# FDM Vault Endpoints
FDM_BASE_URL = os.getenv("LGD_FDM_BASE_URL", "http://fdm.lgdisplay.com:8008")
FDM_SEARCH_URL = os.getenv("LGD_FDM_SEARCH_URL", f"{FDM_BASE_URL}/")
FDM_DETAIL_NONCAD_PATH = "/Windchill/extcore/jsp/lgdfdm/drawing/detailNonCAD.jsp"
FDM_DETAIL_NONCAD_URL = f"{FDM_BASE_URL}{FDM_DETAIL_NONCAD_PATH}"

# Search Default Payload
DEFAULT_SITE = os.getenv("LGD_SITE", "SP")
DEFAULT_FAB = os.getenv("LGD_FAB", "29113")
DEFAULT_VERSION = "latest"
DEFAULT_PAGE_START = "1"
DEFAULT_PAGE_END = "500"

# Session Settings
SESSION_TTL_SECONDS = int(os.getenv("LGD_SESSION_TTL", "7200"))  # 2 hours
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
