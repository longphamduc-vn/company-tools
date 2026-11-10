"""Rule splitting helper to prevent Outlook 64KB/256KB rule quota overflow."""
from typing import List, Tuple


def split_rule_recipients(
    rule_name: str,
    emails: List[str],
    domains: List[str],
    max_recipients: int = 40
) -> List[Tuple[str, List[str], List[str]]]:
    """Split a rule with many recipients into sub-rules for Outlook native engine.
    
    Returns list of (sub_rule_name, email_chunk, domain_chunk).
    Domain matching rules are kept on Part 1.
    """
    if not emails and not domains:
        return [(rule_name, [], [])]

    if len(emails) <= max_recipients:
        return [(rule_name, emails, domains)]

    chunks = []
    # Split emails into slices of max_recipients
    for i in range(0, len(emails), max_recipients):
        part_num = (i // max_recipients) + 1
        sub_name = f"{rule_name} (Part {part_num})"
        email_chunk = emails[i:i + max_recipients]
        # Only assign domains to the first chunk
        domain_chunk = domains if part_num == 1 else []
        chunks.append((sub_name, email_chunk, domain_chunk))

    return chunks

