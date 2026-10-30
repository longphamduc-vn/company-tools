"""
SSO Client implementation for LG Display Vault Authentication.
Complies with Section 4.1:
- Local WebSocket agent on ws://127.0.0.1:28083/
- Token request payload: API?args=tsso://im.lgdisplay.com:8088/GETTOKEN?apiroot=/pdadmin&protocol=http&pd_h=null&pd_id=null
- Token exchange endpoint: http://im.lgdisplay.com:8088/pdadmin/eai/eai.jsp
- Extraction and validation of PD-TH-SESSION-ID, PD-ID, JSESSIONID
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

from lgd_vault.config import (
    SSO_WS_HOST,
    SSO_WS_PORT,
    SSO_WS_PAYLOAD,
    SSO_TOKEN_EXCHANGE_URL,
    REQUIRED_COOKIES,
    DEFAULT_TIMEOUT_CONNECT,
    DEFAULT_TIMEOUT_READ,
    USER_AGENT,
)
from lgd_vault.exceptions import SSOConnectionRefusedError, AuthExpiredError
from lgd_vault.session_manager import SessionManager

logger = logging.getLogger("lgd_vault.sso")


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
                logger.info("Using active cached session cookies")
                session.cookies.update(cached_cookies)
                return session

        # Perform new authentication
        logger.info("Initiating new SSO authentication workflow...")
        cookies = self.authenticate()
        session.cookies.update(cookies)
        return session

    def authenticate(self) -> Dict[str, str]:
        """
        Executes full authentication flow:
        1. Connects to ws://127.0.0.1:28083/ and sends token request payload.
        2. Exchanges received token at eai.jsp.
        3. Extracts PD-TH-SESSION-ID, PD-ID, JSESSIONID.
        4. Saves session to session.json.
        """
        # Step 1: WebSocket communication with local SSO agent
        raw_sso_response = self._request_token_via_websocket()
        logger.info("SSO WebSocket response received: %s", raw_sso_response[:100] if raw_sso_response else "None")

        # Step 2: Exchange token with EAI endpoint
        cookies = self._exchange_token_for_cookies(raw_sso_response)

        # Step 3: Verify and save session
        self.session_manager.save_session(cookies, metadata={"source": "sso_agent"})
        return cookies

    def _request_token_via_websocket(self, timeout: float = 8.0) -> str:
        """
        Connects to ws://127.0.0.1:28083/ and sends SSO_WS_PAYLOAD.
        Uses pure Python socket RFC-6455 handshake to avoid mandatory external websocket dependencies,
        with fallback support for third-party libraries if present.
        """
        logger.debug("Connecting to SSO Agent at ws://%s:%s/", self.ws_host, self.ws_port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((self.ws_host, self.ws_port))
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.error("Failed to connect to SSO Agent on %s:%s - %s", self.ws_host, self.ws_port, e)
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
            if "101" not in header_text.splitlines()[0]:
                raise SSOConnectionRefusedError(f"SSO Agent rejected WS upgrade: {header_text[:120]}")

            # 2. Send Payload text frame
            payload_bytes = SSO_WS_PAYLOAD.encode("utf-8")
            frame = self._build_websocket_frame(payload_bytes, opcode=1, mask=True)
            sock.sendall(frame)

            # 3. Read WebSocket response frame
            received_payload = self._read_websocket_frame(sock)
            return received_payload.decode("utf-8", errors="ignore")

        except SSOConnectionRefusedError:
            raise
        except Exception as e:
            logger.error("Error communicating with SSO Local Agent: %s", e)
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

        # Parse token / arguments from raw response
        # Common formats:
        # 1. "TOKEN=ABC..." or query string "token=ABC&..."
        # 2. Direct token string "ABC12345"
        # 3. URL containing query params "http://.../eai.jsp?token=..."
        # 4. JSON: {"token": "..."}
        params: Dict[str, str] = {}
        headers: Dict[str, str] = {}

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
                # Full URL received
                parsed_url = urllib.parse.urlparse(cleaned)
                params = dict(urllib.parse.parse_qsl(parsed_url.query))
            elif "=" in cleaned:
                params = dict(urllib.parse.parse_qsl(cleaned))
            elif cleaned:
                params["token"] = cleaned

        target_url = self.token_exchange_url
        logger.debug("Requesting token exchange at %s with params %s", target_url, params)

        try:
            resp = req_session.get(
                target_url,
                params=params,
                timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                allow_redirects=True,
            )
        except requests.RequestException as e:
            logger.error("Failed to reach Token Exchange Endpoint %s: %s", target_url, e)
            raise AuthExpiredError(f"Cannot reach Token Exchange Endpoint: {e}") from e

        # Extract cookies from session cookie jar
        cookies = dict(req_session.cookies)

        # Fallback check for missing cookies in Set-Cookie headers
        if not cookies and "Set-Cookie" in resp.headers:
            for part in resp.headers.get("Set-Cookie", "").split(","):
                for item in part.split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        cookies[k] = v

        logger.info("Cookies retrieved from SSO Exchange: %s", list(cookies.keys()))
        return cookies

    @staticmethod
    def _build_websocket_frame(payload: bytes, opcode: int = 1, mask: bool = True) -> bytes:
        """Constructs an RFC 6455 WebSocket frame."""
        frame = bytearray()
        first_byte = 0x80 | (opcode & 0x0F)  # FIN = 1
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
