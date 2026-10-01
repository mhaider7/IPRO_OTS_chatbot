"""Deterministic routing fixtures, not a complete production topic classifier."""
import re

FIXED_TOPICS = (
    r"\bticket\s+(?:status|update)\b|\bstatus\s+of\s+(?:my\s+)?ticket\b",
    r"\b(?:billing|charge|fee)\s+(?:dispute|on my account)\b",
    r"\b(?:dispute|appeal)\b.*\b(?:hold|suspension|violation|charge|fee)\b",
    r"\b(?:my|individual)\s+(?:loan history|license assignment)\b",
)
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
    if "duo" in context and re.search(r"(?:lost|no access|no longer|can't access).*?(?:phone|device)|(?:phone|device).*?(?:lost|broken|no longer)", latest, re.I):
        return True
    return "password" in context and "reset" in context and bool(
        re.search(r"still|didn't work|did not work|not working|won't let", latest, re.I)
    )


def topic_for(text: str) -> str | None:
    for topic, words in (
        ("Wi-Fi", ("wifi", "wi-fi", "eduroam", "wireless")),
        ("password reset", ("password", "myiit", "log in", "login")),
        ("printing", ("print", "printer", "papercut")),
        ("Duo", ("duo", "two-factor", "mfa")),
        ("VPN", ("vpn",)),
        ("software", ("software", "license", "matlab")),
        ("equipment", ("laptop", "equipment", "borrow")),
    ):
        if any(re.search(r"\b" + re.escape(word) + r"(?:s|ing)?\b", text, re.I) for word in words):
            return topic
    return None
