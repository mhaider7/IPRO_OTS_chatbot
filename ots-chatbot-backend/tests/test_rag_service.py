"""RagService with a fake retriever and fake model: every escalation path, no Ollama or index needed."""
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.rag_service import LOW_CONFIDENCE, MODEL_DOWN, NO_MATCH, RagService
from llm.ollama_client import OllamaUnavailable
from retrieval.retriever import Chunk, IndexMissing

WIFI = Chunk("Connect to IIT-Secure and sign in with your Illinois Tech account.", "OTS: Getting Connected",
             "https://www.iit.edu/ots/access/getting-connected", "ots", 0.3)
FAR = Chunk("Unrelated ticket.", "Public IT ticket dataset", "huggingface.co/datasets/x", "ticket", 0.9)


class FakeModel:
    def __init__(self, answer="Connect to IIT-Secure, then sign in.", confidence="high", down=False):
        self.answer, self.confidence, self.down, self.calls = answer, confidence, down, []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if self.down:
            raise OllamaUnavailable("down")
        return self.answer

    def chat_json(self, messages, schema, **kwargs):
        if self.down:
            raise OllamaUnavailable("down")
        props = schema["properties"]
        if "confidence" in props:
            return {"confidence": self.confidence}
        return {"subject": "Wi-Fi will not connect", "summary": "My laptop cannot join IIT-Secure."}


def make_client(chunks=(WIFI,), model=None, retrieve=None):
    model = model or FakeModel()
    service = RagService(retrieve=retrieve or (lambda query: list(chunks)), chat=model.chat, chat_json=model.chat_json)
    return TestClient(create_app(service=service)), model


def ask(client, *texts, mode="conversation"):
    messages = [{"role": "user" if i % 2 == 0 else "bot", "text": text} for i, text in enumerate(texts)]
    return client.post("/api/chat", json={"messages": messages, "mode": mode}).json()


def test_grounded_answer_with_sources():
    client, model = make_client()
    result = ask(client, "My laptop won't connect to the Wi-Fi")
    assert result == {"reply": "Connect to IIT-Secure, then sign in.", "sources": [WIFI.url],
                      "escalate": False, "escalation_reason": None, "offer_options": True}
    system = model.calls[0][0]["content"]
    assert WIFI.text in system and "Hawk" in system


def test_followup_sends_history_to_model():
    client, model = make_client()
    ask(client, "My laptop won't connect to the Wi-Fi", "Try IIT-Secure.", "It still fails on my phone")
    roles = [message["role"] for message in model.calls[0]]
    assert roles == ["system", "user", "assistant", "user"]


@pytest.mark.parametrize("texts,reason", [
    (("What is my ticket status?",), "fixed_topic"),
    (("I reset my password", "Try again.", "It still won't let me in"), "fixed_topic"),
    (("I want to talk to a technician about my Wi-Fi",), "user_request"),
])
def test_fixed_topic_and_user_request_skip_search_and_model(texts, reason):
    calls = []
    client, model = make_client(retrieve=lambda query: calls.append(query) or [WIFI])
    result = ask(client, *texts)
    assert result["escalate"] is True and result["escalation_reason"] == reason
    assert calls == [] and model.calls == []


def test_no_good_match_escalates_without_generation():
    client, model = make_client(chunks=[FAR])
    result = ask(client, "My Bluetooth mouse is not working")
    assert result["escalation_reason"] == "low_confidence" and result["reply"] == NO_MATCH
    assert model.calls == []


def test_low_self_grade_escalates_and_hides_answer():
    client, _ = make_client(model=FakeModel(answer="Made-up steps", confidence="low"))
    result = ask(client, "My laptop won't connect to the Wi-Fi")
    assert result["escalation_reason"] == "low_confidence" and result["reply"] == LOW_CONFIDENCE
    assert result["sources"] == []


def test_ollama_down_returns_friendly_fallback():
    client, _ = make_client(model=FakeModel(down=True))
    result = ask(client, "My laptop won't connect to the Wi-Fi")
    assert result["reply"] == MODEL_DOWN and result["escalate"] is True and result["offer_options"] is True


def test_off_topic_question_stays_out_of_scope():
    client, model = make_client(chunks=[FAR])
    result = ask(client, "How's the weather today?")
    assert result["escalate"] is False and result["offer_options"] is False and model.calls == []


def test_close_match_counts_as_in_scope_even_if_regex_misses():
    client, _ = make_client()
    result = ask(client, "How do I get started with the Virtual Computer Lab?")
    assert result["escalate"] is False and result["sources"] == [WIFI.url]


def test_diagnose_after_button_asks_for_steps():
    client, model = make_client()
    result = ask(client, "My laptop won't connect to the Wi-Fi", "How would you like to continue?", mode="diagnose")
    assert not result["escalate"]
    assert "numbered steps" in model.calls[0][0]["content"]
    assert model.calls[0][-1]["content"].startswith("Please give me troubleshooting steps")


def test_missing_index_falls_back_to_demo_responses():
    def missing(query):
        raise IndexMissing("not built")
    client, _ = make_client(retrieve=missing)
    result = ask(client, "Wi-Fi won't connect")
    assert result["offer_options"] is True and "Wi-Fi" in result["reply"]


def test_escalate_returns_model_email_with_forced_recipient():
    client, _ = make_client()
    result = client.post("/api/escalate", json={"messages": [{"role": "user", "text": "My laptop will not join IIT-Secure, error: authentication failed"}]}).json()
    assert result["clarifying_question"] is None
    assert result["email"]["to"] == "supportdesk@illinoistech.edu"
    assert result["email"]["subject"] == "OTS Support Request: Wi-Fi will not connect"
