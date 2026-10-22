"""Email drafts for OTS: LLM-written from the conversation, with a template fallback."""
import re

from api.schemas import Conversation, EmailDraft, EscalationResponse
from common.redact import redact_identifiers  # noqa: F401  (re-exported for existing imports)
from escalation.topics import topic_for
from llm import ollama_client
from llm.prompts import EMAIL_PROMPT, EMAIL_SCHEMA, REASON_LINES, transcript

OTS_ADDRESS = "supportdesk@illinoistech.edu"  # api/main.py replaces this with the configured recipient.
CLARIFY_ISSUE = "What problem would you like OTS to help with? Use fictional details for this demo; do not include personal identifiers or passwords."
CLARIFY_DETAIL = "What device or error message is involved? You can say 'skip' if you do not know. Please leave out personal identifiers and passwords."
QUESTIONS = {CLARIFY_ISSUE, CLARIFY_DETAIL}
SUBJECT_PREFIX = "OTS Support Request: "


def already_asked(conversation: Conversation) -> bool:
    return any(message.role == "bot" and message.text in QUESTIONS for message in conversation.messages)


def build_test_email(conversation: Conversation) -> EscalationResponse:
    """Template draft that preserves the student's words without inventing facts."""
    users = [message.text for message in conversation.messages if message.role == "user"]
    asked = already_asked(conversation)
    if not asked and not users:
        return EscalationResponse(clarifying_question=CLARIFY_ISSUE)
    if not asked and len(users) == 1 and len(users[0].split()) < 8:
        return EscalationResponse(clarifying_question=CLARIFY_DETAIL)
    details = [redact_identifiers(text) for text in users if text.lower().strip() != "skip"]
    topic = next((topic_for(text) for text in reversed(users) if topic_for(text)), "IT assistance")
    summary = "\n".join(f"- {text}" for text in details) or "[Describe the issue before sending.]"
    return EscalationResponse(email=EmailDraft(
        to=OTS_ADDRESS,
        subject=f"{SUBJECT_PREFIX}{topic}",
        body=("Hello OTS Support Desk,\n\nI would appreciate help with the following issue. "
              "These are the details I shared:\n\n" + summary +
              "\n\nCould you advise me on the next steps?\n\nThank you."),
    ))


def clean_subject(subject: str, fallback: str) -> str:
    subject = re.sub(r"\s+", " ", redact_identifiers(subject or "")).strip()
    subject = re.sub(r"^(?:subject:\s*)?(?:OTS Support Request:\s*)?", "", subject, flags=re.I) or fallback
    return (SUBJECT_PREFIX + subject)[:120].rstrip()


def draft_email(conversation: Conversation, reason: str | None = None, chat_json=None) -> EscalationResponse:
    """Ask at most one clarifying question, then draft the email with a model-written summary."""
    chat_json = chat_json or ollama_client.chat_json
    users = [message.text for message in conversation.messages if message.role == "user"]
    asked = already_asked(conversation)
    if not users and not asked:
        return EscalationResponse(clarifying_question=CLARIFY_ISSUE)
    if not users:
        return build_test_email(conversation)
    try:
        # Only the student's own words: summarizing Hawk's replies made the model restate them as the student's.
        chat_text = redact_identifiers(transcript([message for message in conversation.messages if message.role == "user"]))
        # Deterministic on purpose: llama3.2:3b asked for details students had already given.
        if not asked and len(users) == 1 and len(users[0].split()) < 8:
            return EscalationResponse(clarifying_question=CLARIFY_DETAIL)
        draft = chat_json([{"role": "user", "content": EMAIL_PROMPT.format(
            reason_line=REASON_LINES.get(reason or "", ""), transcript=chat_text)}], EMAIL_SCHEMA, temperature=0)
        summary = re.sub(r"\s+", " ", redact_identifiers(str(draft.get("summary") or ""))).strip()
        if not summary:
            raise ollama_client.OllamaUnavailable("empty email summary")
        if summary[-1] not in ".!?":
            summary += "."
        details = "\n".join(f"- {redact_identifiers(text)}" for text in users if text.lower().strip() != "skip")
        body = (f"Hello OTS Support Desk,\n\n{summary}\n\nWhat I told the Hawk assistant:\n{details}\n\n"
                "Could you advise me on the next steps?\n\nThank you,\n[Your Name]")
        topic = next((topic_for(text) for text in reversed(users) if topic_for(text)), "IT assistance")
        return EscalationResponse(email=EmailDraft(to=OTS_ADDRESS, subject=clean_subject(str(draft.get("subject") or ""), topic), body=body))
    except ollama_client.OllamaUnavailable:
        # Escalation must never fail outright; the template still gives a reviewable draft.
        return build_test_email(conversation)
