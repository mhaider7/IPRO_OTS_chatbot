"""Shared identifier masking for source data, chat excerpts, and email drafts."""
import re


def redact_identifiers(text: str) -> str:
    # Defense in depth for common accidental identifiers; not a general PII detector.
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email omitted]", text)
    text = re.sub(r"\b[Aa]\d{8}\b", "[student ID omitted]", text)
    text = re.sub(r"(?i)\b(student\s*id|password|verification code|mfa code)\s*(?:is|:|=)\s*\S+", r"\1 [omitted]", text)
    return text
