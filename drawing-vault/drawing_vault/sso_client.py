"""
SSO Client implementation for Drawing Vault Authentication.
Complies with Section 4.1:
- Local WebSocket agent on ws://127.0.0.1:28083/
- Token request payload: API?args=tsso://im.internal.net:8088/GETTOKEN?apiroot=/pdadmin&protocol=http&pd_h=null&pd_id=null
- Token exchange endpoint: http://im.internal.net:8088/pdadmin/eai/eai.jsp
- Extraction and validation of PD-TH-SESSION-ID, PD-ID, JSESSIONID
Includes comprehensive step-by-step diagnostic logging.
"""

import base64
import json
import logging
import os
import re
import socket
import struct
import urllib.parse
from typing import Dict, Optional, Tuple

import requests

from drawing_vault.config import (
    SSO_WS_HOST,
    SSO_WS_PORT,
    SSO_WS_PAYLOAD,
    SSO_TOKEN_EXCHANGE_URL,
    REQUIRED_COOKIES,
    DEFAULT_TIMEOUT_CONNECT,
    DEFAULT_TIMEOUT_READ,
    USER_AGENT,
)
from drawing_vault.exceptions import SSOConnectionRefusedError, AuthExpiredError
from drawing_vault.session_manager import SessionManager

logger = logging.getLogger("drawing_vault.sso")


class SSOClient:
    """Handles communication with SSO local desktop agent and cookie retrieval."""

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        ws_host: str = SSO_WS_HOST,
        ws_port: int = SSO_WS_PORT,
        token_exchange_url: str = SSO_TOKEN_EXCHANGE_URL,
    ):
        self.session_manager = session_manager or SessionManager()
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.token_exchange_url = token_exchange_url

    def get_authenticated_session(self, force_refresh: bool = False) -> requests.Session:
        """
        Returns a requests.Session populated with valid cookies.
        Uses cached session from session.json if available and not expired.
        Otherwise performs the full SSO handshake.
        """
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        if not force_refresh:
            cached_cookies = self.session_manager.load_session()
            if cached_cookies:
                logger.info(
                    "Using active cached session cookies: %s (expires soon)",
                    list(cached_cookies.keys()),
                )
                session.cookies.update(cached_cookies)
                return session

        # Perform new authentication
        logger.info("Initiating new SSO authentication workflow...")
        cookies = self.authenticate()
        session.cookies.update(cookies)
        return session

    def authenticate(self) -> Dict[str, str]:
        """
        Executes full authentication flow with detailed diagnostics:
        1. Connects to ws://127.0.0.1:28083/ and sends token request payload.
        2. Exchanges received token at eai.jsp.
        3. Extracts PD-TH-SESSION-ID, PD-ID, JSESSIONID.
        4. Saves session to session.json.
        """
        logger.info("--- [SSO AUTH] Step 1: Connecting to Local SSO Agent ws://%s:%s/ ---", self.ws_host, self.ws_port)
        raw_sso_response = self._request_token_via_websocket()
        logger.info("[SSO AUTH] Step 1 SUCCESS: Received raw token response (%d chars): %s", len(raw_sso_response), repr(raw_sso_response[:200]))

        logger.info("--- [SSO AUTH] Step 2: Token Exchange at %s ---", self.token_exchange_url)
        cookies = self._exchange_token_for_cookies(raw_sso_response)

        # Check for required cookies
        missing = [c for c in REQUIRED_COOKIES if c not in cookies]
        if missing:
            logger.warning("[SSO AUTH] Warning: Missing expected cookies: %s. Present: %s", missing, list(cookies.keys()))
        else:
            logger.info("[SSO AUTH] All required cookies present: %s", list(cookies.keys()))

        # Save session
        self.session_manager.save_session(cookies, metadata={"source": "sso_agent"})
        logger.info("[SSO AUTH] Session saved to %s", self.session_manager.session_file)
        return cookies

    def _request_token_via_websocket(self, timeout: float = 8.0) -> str:
        """
        Connects to ws://127.0.0.1:28083/ and sends SSO_WS_PAYLOAD.
        Uses pure Python socket RFC-6455 handshake with diagnostic logging.
        """
        logger.debug("Opening TCP socket to %s:%s...", self.ws_host, self.ws_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((self.ws_host, self.ws_port))
            logger.debug("Connected to %s:%s successfully.", self.ws_host, self.ws_port)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.error("[SSO ERROR] Failed to connect to SSO Agent on %s:%s - %s", self.ws_host, self.ws_port, e)
            logger.error(
                "[SSO DIAGNOSTIC] Cause: The SSO local Agent software is not running or port %s is blocked. "
                "Action: Please launch SSO software on your PC.",
                self.ws_port,
            )
            raise SSOConnectionRefusedError() from e

        try:
            # 1. Send WebSocket Upgrade Request
            nonce_key = base64.b64encode(os.urandom(16)).decode("ascii")
            handshake = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.ws_host}:{self.ws_port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {nonce_key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"Origin: http://{self.ws_host}:{self.ws_port}\r\n"
                f"\r\n"
            )
            sock.sendall(handshake.encode("ascii"))

            # Read Handshake Response
            response_data = b""
            while b"\r\n\r\n" not in response_data:
                chunk = sock.recv(2048)
                if not chunk:
                    break
                response_data += chunk

            header_text = response_data.decode("utf-8", errors="ignore")
            logger.debug("WebSocket Handshake Response Header:\n%s", header_text.strip())

            if "101" not in header_text.splitlines()[0]:
                err_msg = f"SSO Agent rejected WS upgrade: {header_text[:120]}"
                logger.error("[SSO ERROR] %s", err_msg)
                raise SSOConnectionRefusedError(err_msg)

            # 2. Send Payload text frame
            logger.info("[SSO AUTH] Sending WebSocket payload: %s", SSO_WS_PAYLOAD)
            payload_bytes = SSO_WS_PAYLOAD.encode("utf-8")
            frame = self._build_websocket_frame(payload_bytes, opcode=1, mask=True)
            sock.sendall(frame)

            # 3. Read WebSocket response frame
            received_payload = self._read_websocket_frame(sock)
            resp_str = received_payload.decode("utf-8", errors="ignore")
            logger.debug("[SSO AUTH] Received frame payload (%d bytes): %s", len(received_payload), resp_str)
            return resp_str

        except SSOConnectionRefusedError:
            raise
        except Exception as e:
            logger.exception("[SSO ERROR] Communication error with local SSO agent on port %s: %s", self.ws_port, e)
            raise SSOConnectionRefusedError(f"SSO Local Agent communication failed: {e}") from e
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _exchange_token_for_cookies(self, sso_resp: str) -> Dict[str, str]:
        """
        Sends token/query parameters to SSO_TOKEN_EXCHANGE_URL (eai.jsp)
        and extracts PD-TH-SESSION-ID, PD-ID, JSESSIONID from response cookies.
        """
        req_session = requests.Session()
        req_session.headers.update({"User-Agent": USER_AGENT})

        params: Dict[str, str] = {}
        cleaned = (sso_resp or "").strip()

        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                data = json.loads(cleaned)
                if "token" in data:
                    params["token"] = data["token"]
                elif "args" in data:
                    params["args"] = data["args"]
            except Exception:
                pass

        if not params:
            if "://" in cleaned and "?" in cleaned:
                parsed_url = urllib.parse.urlparse(cleaned)
                params = dict(urllib.parse.parse_qsl(parsed_url.query))
            elif "=" in cleaned:
                params = dict(urllib.parse.parse_qsl(cleaned))
            elif cleaned:
                params["token"] = cleaned

        target_url = self.token_exchange_url
        logger.info("[SSO AUTH] Calling EAI Token Exchange URL: %s with params: %s", target_url, params)

        try:
            resp = req_session.get(
                target_url,
                params=params,
                timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                allow_redirects=True,
            )
            logger.info(
                "[SSO AUTH] EAI Response: HTTP %d (URL: %s, Time: %.2fs)",
                resp.status_code,
                resp.url,
                resp.elapsed.total_seconds(),
            )
            logger.debug("[SSO AUTH] EAI Response Headers: %s", dict(resp.headers))
            logger.debug("[SSO AUTH] EAI Response Body Preview: %s", resp.text[:300])

        except requests.RequestException as e:
            logger.error("[SSO ERROR] Failed to reach Token Exchange Endpoint %s: %s", target_url, e)
            raise AuthExpiredError(f"Cannot reach Token Exchange Endpoint: {e}") from e

        cookies = dict(req_session.cookies)

        # Fallback check for Set-Cookie header
        if not cookies and "Set-Cookie" in resp.headers:
            for part in resp.headers.get("Set-Cookie", "").split(","):
                for item in part.split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        cookies[k] = v

        logger.info("[SSO AUTH] Cookies received from SSO Exchange: %s", list(cookies.keys()))
        return cookies

    @staticmethod
    def _build_websocket_frame(payload: bytes, opcode: int = 1, mask: bool = True) -> bytes:
        """Constructs an RFC 6455 WebSocket frame."""
        frame = bytearray()
        first_byte = 0x80 | (opcode & 0x0F)
        frame.append(first_byte)

        length = len(payload)
        mask_bit = 0x80 if mask else 0x00

        if length <= 125:
            frame.append(mask_bit | length)
        elif length <= 65535:
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))

        if mask:
            mask_key = os.urandom(4)
            frame.extend(mask_key)
            masked_payload = bytearray(length)
            for i in range(length):
                masked_payload[i] = payload[i] ^ mask_key[i % 4]
            frame.extend(masked_payload)
        else:
            frame.extend(payload)

        return bytes(frame)

    @staticmethod
    def _read_websocket_frame(sock: socket.socket) -> bytes:
        """Reads and decodes an RFC 6455 WebSocket frame."""
        head = sock.recv(2)
        if len(head) < 2:
            return b""

        first_byte, second_byte = head[0], head[1]
        is_masked = bool(second_byte & 0x80)
        payload_len = second_byte & 0x7F

        if payload_len == 126:
            ext_len = sock.recv(2)
            payload_len = struct.unpack("!H", ext_len)[0]
        elif payload_len == 127:
            ext_len = sock.recv(8)
            payload_len = struct.unpack("!Q", ext_len)[0]

        mask_key = sock.recv(4) if is_masked else b""

        payload = b""
        while len(payload) < payload_len:
            chunk = sock.recv(min(4096, payload_len - len(payload)))
            if not chunk:
                break
            payload += chunk

        if is_masked and mask_key:
            unmasked = bytearray(len(payload))
            for i in range(len(payload)):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            return bytes(unmasked)

        return payload
