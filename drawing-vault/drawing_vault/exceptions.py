"""
Exceptions and Error Codes conforming to Section 7 of AI Agent Technical Specification.
"""

class VaultAutomationError(Exception):
    """Base exception for LGD Drawing Vault automation errors."""
    code: str = "VAULT_ERROR"
    recovery_action: str = ""

    def __init__(self, message: str, code: str = None, recovery_action: str = None):
        super().__init__(message)
        if code:
            self.code = code
        if recovery_action:
            self.recovery_action = recovery_action


class SSOConnectionRefusedError(VaultAutomationError):
    """
    Code: WS_CONN_REFUSED
    Cause: SSO Local Agent software not running on user PC.
    Recovery Action: Inform user to open LG Display SSO Agent software on port 28083.
    """
    code: str = "WS_CONN_REFUSED"
    recovery_action: str = (
        "Inform user to open LG Display SSO Agent software on port 28083 "
        "(ws://127.0.0.1:28083/)."
    )

    def __init__(self, message: str = None):
        default_msg = (
            "Authentication Failed: SSO Local Agent on port 28083 is not responding or session rejected. "
            "Please ensure the LG Display SSO Agent software is running on your machine."
        )
        super().__init__(message or default_msg, code=self.code, recovery_action=self.recovery_action)


class AuthExpiredError(VaultAutomationError):
    """
    Code: HTTP_401 / HTTP_403
    Cause: Cookies expired or invalid session.
    Recovery Action: Force clear session.json and re-trigger authenticate().
    """
    code: str = "HTTP_401"
    recovery_action: str = "Force clear session.json and re-trigger authenticate()."

    def __init__(self, message: str = "Authentication session expired or rejected (401/403).", code: str = "HTTP_401"):
        super().__init__(message, code=code, recovery_action=self.recovery_action)


class DrawingNotFoundError(VaultAutomationError):
    """
    Code: DRAWING_NOT_FOUND
    Cause: QCode invalid or no Non-CAD drawings available.
    Recovery Action: Report missing QCode directly to user for verification.
    """
    code: str = "DRAWING_NOT_FOUND"
    recovery_action: str = "Report missing QCode directly to user for verification."

    def __init__(self, qcode: str, message: str = None):
        msg = message or f"Failed: Drawing Not Found for QCode '{qcode}' (no non-CAD visual assets available)."
        super().__init__(msg, code=self.code, recovery_action=self.recovery_action)
        self.qcode = qcode


class CorruptPayloadError(VaultAutomationError):
    """
    Code: CORRUPT_PAYLOAD
    Cause: Server returned HTML login page instead of binary stream.
    Recovery Action: Re-authenticate session and retry download stream once.
    """
    code: str = "CORRUPT_PAYLOAD"
    recovery_action: str = "Re-authenticate session and retry download stream once."

    def __init__(self, message: str = "Server returned HTML login page instead of binary drawing stream."):
        super().__init__(message, code=self.code, recovery_action=self.recovery_action)
