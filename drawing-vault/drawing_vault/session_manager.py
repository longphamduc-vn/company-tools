"""
Session management and persistence for SSO Cookies.
Complies with Section 4.1.5 & 4.1.6 of the specification:
- Session file backup: session.json (Default TTL: 7200s / 2 hours)
- Required session cookies: PD-TH-SESSION-ID, PD-ID, JSESSIONID
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Any

from drawing_vault.config import (
    DEFAULT_SESSION_FILE,
    SESSION_TTL_SECONDS,
    REQUIRED_COOKIES,
)

logger = logging.getLogger("drawing_vault.session")


class SessionManager:
    """Manages reading, storing, verifying, and invalidating local SSO session cookies."""

    def __init__(self, session_file: str = DEFAULT_SESSION_FILE, ttl_seconds: int = SESSION_TTL_SECONDS):
        self.session_file = session_file
        self.ttl_seconds = ttl_seconds

    def save_session(self, cookies: Dict[str, str], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Saves session cookies to session.json with timestamp and expiration.
        """
        now = time.time()
        expires_at = now + self.ttl_seconds

        session_payload = {
            "created_at": now,
            "expires_at": expires_at,
            "ttl_seconds": self.ttl_seconds,
            "cookies": cookies,
            "metadata": metadata or {},
        }

        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.session_file)), exist_ok=True)

        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(session_payload, f, indent=2)
            logger.info("Session successfully saved to %s (valid for %ds)", self.session_file, self.ttl_seconds)
        except Exception as e:
            logger.error("Failed to write session file %s: %s", self.session_file, e)
            raise

    def load_session(self) -> Optional[Dict[str, str]]:
        """
        Loads cookies from session.json if the file exists and has not expired.
        Returns cookie dict or None if expired/corrupted/missing.
        """
        if not os.path.isfile(self.session_file):
            logger.debug("No session file found at %s", self.session_file)
            return None

        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            expires_at = data.get("expires_at", 0)
            now = time.time()

            if now >= expires_at:
                logger.warning("Session in %s has expired (expired at %s, now %s)", self.session_file, expires_at, now)
                return None

            cookies = data.get("cookies", {})
            if not isinstance(cookies, dict):
                return None

            # Verify that required cookies exist or at least non-empty cookies are present
            if not any(k in cookies for k in REQUIRED_COOKIES):
                logger.warning("Session file does not contain required cookies (%s)", REQUIRED_COOKIES)

            logger.info("Valid session loaded from %s (expires in %.0fs)", self.session_file, expires_at - now)
            return cookies

        except Exception as e:
            logger.warning("Failed to parse session file %s: %s. Invalidation recommended.", self.session_file, e)
            return None

    def is_session_valid(self) -> bool:
        """Checks if current session is active and not expired."""
        return self.load_session() is not None

    def clear_session(self) -> None:
        """Deletes session.json on 401/403 or manual reset."""
        if os.path.exists(self.session_file):
            try:
                os.remove(self.session_file)
                logger.info("Cleared session file: %s", self.session_file)
            except OSError as e:
                logger.warning("Error removing session file %s: %s", self.session_file, e)

    def get_session_info(self) -> Dict[str, Any]:
        """Provides status inspection for UI or AI Agent reporting."""
        if not os.path.isfile(self.session_file):
            return {"exists": False, "valid": False, "remaining_seconds": 0, "cookies": []}

        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            expires_at = data.get("expires_at", 0)
            now = time.time()
            valid = now < expires_at
            remaining = max(0, int(expires_at - now)) if valid else 0
            cookies = list(data.get("cookies", {}).keys())
            return {
                "exists": True,
                "valid": valid,
                "remaining_seconds": remaining,
                "created_at": data.get("created_at"),
                "expires_at": expires_at,
                "cookies": cookies,
            }
        except Exception:
            return {"exists": True, "valid": False, "remaining_seconds": 0, "cookies": []}
