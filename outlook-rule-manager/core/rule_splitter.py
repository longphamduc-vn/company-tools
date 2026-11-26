"""Rule splitting helper to prevent Outlook 64KB/256KB rule quota overflow."""
from typing import List, Tuple


def _split_values(base_name: str, values: List[str], max_recipients: int) -> List[Tuple[str, List[str]]]:
    """Split a non-empty condition list into (sub_rule_name, chunk) pairs."""
    if len(values) <= max_recipients:
        return [(base_name, values)]
    return [
        (f"{base_name} (Part {(i // max_recipients) + 1})", values[i:i + max_recipients])
        for i in range(0, len(values), max_recipients)
    ]


def split_rule_recipients(
    rule_name: str,
    emails: List[str],
    domains: List[str],
    max_recipients: int = 40
) -> List[Tuple[str, List[str], List[str]]]:
    """Split emails and domains separately into sub-rules within max_recipients.

    Returns list of (sub_rule_name, email_chunk, domain_chunk).
    Email and domain conditions are never combined in one sub-rule because
    Outlook evaluates multiple condition types as AND rather than OR.
    If max_recipients <= 0, falls back to default 40.
    """
    if max_recipients <= 0:
        max_recipients = 40

    email_list = list(emails or [])
    domain_list = list(domains or [])
    chunks: List[Tuple[str, List[str], List[str]]] = []

    if email_list:
        for sub_name, chunk in _split_values(rule_name, email_list, max_recipients):
            chunks.append((sub_name, chunk, []))

    if domain_list:
        for sub_name, chunk in _split_values(f"{rule_name} (Domains)", domain_list, max_recipients):
            chunks.append((sub_name, [], chunk))

    return chunks

