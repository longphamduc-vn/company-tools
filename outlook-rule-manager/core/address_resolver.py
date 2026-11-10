"""Email address normalization and Exchange X.500 resolver."""
import re
from typing import Optional, Tuple

PR_SENT_REPRESENTING_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


def normalize_email(email_str: Optional[str]) -> str:
    """Normalize email string to lowercase stripped standard form."""
    if not email_str:
        return ""
    email = email_str.strip().lower()
    # Remove surrounding brackets or angle brackets: <user@domain.com>
    email = re.sub(r"^[<\[\(]+|[>\]\)]+$", "", email).strip()
    return email


def extract_domain(email_str: str) -> str:
    """Extract @domain.com from email address."""
    email = normalize_email(email_str)
    if "@" in email:
        return "@" + email.split("@", 1)[1]
    return ""


def resolve_outlook_sender(mail_item) -> Tuple[str, str]:
    """Resolve Outlook MailItem sender to (name, smtp_email).
    
    Handles internal Exchange X.500 addresses (/O=EXCHANGELABS/...)
    by querying ExchangeUser or MAPI PropertyAccessor.
    """
    sender_name = ""
    sender_email = ""

    try:
        sender_name = getattr(mail_item, "SenderName", "") or ""
    except Exception:
        pass

    try:
        email_type = getattr(mail_item, "SenderEmailType", "") or ""
        raw_email = getattr(mail_item, "SenderEmailAddress", "") or ""

        if email_type.upper() == "EX":
            # Attempt 1: Sender.GetExchangeUser()
            try:
                sender_obj = mail_item.Sender
                if sender_obj:
                    ex_user = sender_obj.GetExchangeUser()
                    if ex_user and getattr(ex_user, "PrimarySmtpAddress", None):
                        sender_email = ex_user.PrimarySmtpAddress
            except Exception:
                pass

            # Attempt 2: Sender.GetExchangeDistributionList()
            if not sender_email:
                try:
                    sender_obj = mail_item.Sender
                    if sender_obj:
                        ex_dl = sender_obj.GetExchangeDistributionList()
                        if ex_dl and getattr(ex_dl, "PrimarySmtpAddress", None):
                            sender_email = ex_dl.PrimarySmtpAddress
                except Exception:
                    pass

            # Attempt 3: MAPI PropertyAccessor PR_SENT_REPRESENTING_SMTP_ADDRESS
            if not sender_email:
                try:
                    prop_accessor = mail_item.PropertyAccessor
                    smtp = prop_accessor.GetProperty(PR_SENT_REPRESENTING_SMTP_ADDRESS)
                    if smtp and "@" in str(smtp):
                        sender_email = str(smtp)
                except Exception:
                    pass

            # Attempt 4: MAPI PropertyAccessor PR_SMTP_ADDRESS
            if not sender_email:
                try:
                    prop_accessor = mail_item.PropertyAccessor
                    smtp = prop_accessor.GetProperty(PR_SMTP_ADDRESS)
                    if smtp and "@" in str(smtp):
                        sender_email = str(smtp)
                except Exception:
                    pass

            # Fallback if unresolved
            if not sender_email:
                sender_email = raw_email
        else:
            sender_email = raw_email

    except Exception:
        sender_email = ""

    return sender_name.strip(), normalize_email(sender_email)

