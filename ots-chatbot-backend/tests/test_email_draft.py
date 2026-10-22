from api.schemas import Conversation
from escalation.email_builder import CLARIFY_DETAIL, CLARIFY_ISSUE, build_test_email, draft_email
from llm.ollama_client import OllamaUnavailable


def conversation(*texts):
    return Conversation(messages=[{"role": "user" if i % 2 == 0 else "bot", "text": text} for i, text in enumerate(texts)])


def model(subject="Printer jam", summary=None):
    calls = []

    def chat_json(messages, schema, **kwargs):
        calls.append(messages[0]["content"])
        return {"subject": subject, "summary": summary or "The library printer keeps jamming."}

    return chat_json, calls


def test_email_shape_and_placeholders():
    chat_json, calls = model()
    result = draft_email(conversation("The printer in the library keeps jamming, error E-52"), "low_confidence", chat_json=chat_json)
    assert result.clarifying_question is None
    assert result.email.to == "supportdesk@illinoistech.edu"
    assert result.email.subject == "OTS Support Request: Printer jam"
    assert result.email.body.startswith("Hello OTS Support Desk,\n\nThe library printer keeps jamming.")
    assert "- The printer in the library keeps jamming, error E-52" in result.email.body  # Student's own words.
    assert result.email.body.endswith("[Your Name]")
    assert "could not find verified self-service steps" in calls[-1]


def test_asks_one_clarifying_question_for_short_reports_then_drafts():
    chat_json, calls = model()
    first = draft_email(conversation("Wi-Fi is broken"), chat_json=chat_json)
    assert first.email is None and first.clarifying_question == CLARIFY_DETAIL and calls == []
    second = draft_email(conversation("Wi-Fi is broken", first.clarifying_question, "skip"), chat_json=chat_json)
    assert second.email is not None and "- skip" not in second.email.body


def test_detailed_report_drafts_without_question():
    chat_json, _ = model()
    result = draft_email(conversation("My MacBook will not join IIT-Secure in Galvin Library, it says authentication failed"), chat_json=chat_json)
    assert result.clarifying_question is None and result.email is not None


def test_empty_conversation_asks_for_the_issue():
    chat_json, calls = model()
    assert draft_email(conversation(), chat_json=chat_json).clarifying_question == CLARIFY_ISSUE
    assert calls == []


def test_redacts_identifiers_in_prompt_and_draft():
    chat_json, calls = model(subject="Help for A12345678", summary="My password: hunter2 and A12345678, write me at me@example.com")
    result = draft_email(conversation("Locked out, my student id is A12345678 and email me@example.com"), chat_json=chat_json)
    assert "A12345678" not in calls[0] and "me@example.com" not in calls[0]
    text = result.email.subject + result.email.body
    assert "A12345678" not in text and "hunter2" not in text and "me@example.com" not in text


def test_subject_is_single_line_and_capped():
    chat_json, _ = model(subject="OTS Support Request: " + "very long\nsubject " * 40)
    subject = draft_email(conversation("The printer in the library keeps jamming on every page"), chat_json=chat_json).email.subject
    assert "\n" not in subject and len(subject) <= 120 and subject.count("OTS Support Request:") == 1


def test_falls_back_to_template_when_model_down():
    def down(messages, schema, **kwargs):
        raise OllamaUnavailable("down")
    convo = conversation("The printer in the library keeps jamming with error E-52")
    assert draft_email(convo, chat_json=down) == build_test_email(convo)
