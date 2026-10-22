"""Fixed escalation topics: questions that always need OTS to look up one student's record.

This is the only place the list changes. Checks run before any retrieval or generation.
"""
import re

FIXED_TOPICS = (
    # Status of an existing support ticket.
    r"\bticket\s+(?:status|update|number)\b|\bstatus\s+of\s+(?:my\s+)?(?:support\s+)?ticket\b|\b(?:my|the)\s+ticket\b.*\b(?:update|status|resolved|closed)\b",
    # A specific charge, fee, or billing dispute on someone's account.
    r"\b(?:billing|charge|charged|fee|fine)\s+(?:dispute|on my account)\b|\b(?:charged|billed)\s+(?:me|twice)\b|\b(?:print(?:ing)?|equipment|late)\s+(?:charge|fee)\b.*\b(?:my|wrong|refund)\b",
    # Disputing a hold, suspension, or policy violation.
    r"\b(?:dispute|appeal)\b.*\b(?:hold|suspension|violation|charge|fee)\b|\b(?:hold|suspension|suspended|disabled)\b.*\bmy\s+account\b|\bmy\s+account\b.*\b(?:suspended|disabled|on hold|locked by)\b",
    # Looking up or changing something tied to one person's record.
    r"\b(?:my|individual)\s+(?:loan history|license assignment|equipment loan|rental history)\b",
)
MFA = r"duo|okta|two-factor|2fa|mfa|multi-?factor|authenticator"
HUMAN_REQUEST = r"\b(?:talk|speak|connect)\b.*\b(?:technician|human|person)\b"

UNRELATED = r"\b(?:weather|forecast|raining|rain|snow|recipe|recipes|joke|jokes|horoscope|sports? scores?|football|basketball|movie recommendation)\b"
TECH_PROBLEM = r"\b(?:error|broken|crash\w*|won't (?:connect|open|load|start|work|boot)|not (?:working|loading|updating)|can't (?:connect|open|access|log in))\b"
TECH_OBJECT = r"\b(?:computer|desktop|device|phone|tablet|app|application|browser|screen|monitor|bluetooth|email|outlook|keyboard|mouse|camera|microphone|zoom|teams)\b"


def support_issue(text: str) -> bool:
    """Conservative demo scope gate; keep real tech failures involving other topics."""
    trouble = bool(re.search(TECH_PROBLEM, text, re.I))
    if re.search(UNRELATED, text, re.I) and not trouble:
        return False
    return bool(topic_for(text) or (trouble and re.search(TECH_OBJECT, text, re.I)))


def in_support_scope(latest: str, user_history: list[str]) -> bool:
    if support_issue(latest):
        return True
    # An explicit topic change must not inherit an earlier Wi-Fi/password issue.
    if re.search(UNRELATED, latest, re.I):
        return False
    if any(re.search(pattern, latest, re.I) for pattern in FIXED_TOPICS) or re.search(HUMAN_REQUEST, latest, re.I):
        return True
    if re.search(r"\b(that|it|still|same|tried|yes|no)\b", latest, re.I):
        return any(support_issue(text) for text in user_history[-4:-1])
    return False


def fixed_topic(latest: str, user_history: list[str]) -> bool:
    if any(re.search(pattern, latest, re.I) for pattern in FIXED_TOPICS):
        return True
    context = " ".join(user_history[-4:]).lower()
    if re.search(MFA, context, re.I) and re.search(r"(?:lost|no access|no longer|can't access).*?(?:phone|device)|(?:phone|device).*?(?:lost|broken|no longer)", latest, re.I):
        return True
    return "password" in context and "reset" in context and bool(
        re.search(r"still|didn't work|did not work|not working|won't let", latest, re.I)
    )


def is_fixed_topic(latest: str, user_history: list[str]) -> bool:
    """Guide name for the fixed-topic check; user_history includes the latest message."""
    return fixed_topic(latest, user_history)


def topic_for(text: str) -> str | None:
    for topic, words in (
        ("Wi-Fi", ("wifi", "wi-fi", "eduroam", "wireless", "iit-secure", "iit-connect")),
        ("password reset", ("password", "myiit", "log in", "login")),
        ("printing", ("print", "printer", "papercut")),
        ("multi-factor authentication", ("duo", "okta", "two-factor", "mfa", "multifactor")),
        ("VPN", ("vpn",)),
        ("software", ("software", "license", "matlab")),
        ("equipment", ("laptop", "equipment", "borrow")),
    ):
        if any(re.search(r"\b" + re.escape(word) + r"(?:s|ing)?\b", text, re.I) for word in words):
            return topic
    return None
