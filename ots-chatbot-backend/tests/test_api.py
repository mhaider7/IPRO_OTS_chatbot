import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.service import DemoService


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def message(text, role="user"):
    return {"role": role, "text": text}


def test_health_and_frontend(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert 'id="launcher"' in client.get("/").text
    assert client.get("/assets/hawk.js").status_code == 200


def test_chat_contract_and_followup(client):
    history = [message("Wi-Fi won't connect")]
    result = client.post("/api/chat", json={"messages": history}).json()
    assert set(result) == {"reply", "sources", "escalate", "escalation_reason", "offer_options"}
    assert result["offer_options"] is True
    assert result["sources"] == []  # Do not fabricate citations.
    assert result["escalate"] is False and result["escalation_reason"] is None
    history += [message(result["reply"], "bot"), message("It still does that on my phone")]
    followup = client.post("/api/chat", json={"messages": history}).json()
    assert "Wi-Fi" in followup["reply"] and not followup["escalate"]


@pytest.mark.parametrize("text,reason", [
    ("What is my ticket status?", "fixed_topic"),
    ("I want to talk to a technician", "user_request"),
    ("My Bluetooth mouse is not working", "low_confidence"),
])
def test_escalation_triggers(client, text, reason):
    result = client.post("/api/chat", json={"messages": [message(text)]}).json()
    assert result["escalate"] is True
    assert result["escalation_reason"] == reason


def test_account_problem_uses_context(client):
    result = client.post("/api/chat", json={"messages": [message("I reset my password"), message("It still won't let me in")]}).json()
    assert result["escalation_reason"] == "fixed_topic"


def test_escalation_clarifies_once_then_returns_reviewable_email(client):
    history = []
    first = client.post("/api/escalate", json={"messages": history}).json()
    assert first["email"] is None and first["clarifying_question"]
    history += [message(first["clarifying_question"], "bot"), message("Wi-Fi is broken")]
    result = client.post("/api/escalate", json={"messages": history}).json()
    assert result["clarifying_question"] is None
    assert result["email"]["to"] == "supportdesk@illinoistech.edu"
    assert "Wi-Fi is broken" in result["email"]["body"]
    assert "[Your Student ID]" not in result["email"]["body"]
    assert client.post("/api/escalate", json={"messages": history}).json() == result


def test_diagnosis_can_follow_a_bot_message(client):
    result = client.post("/api/chat", json={"messages": [message("Wi-Fi won't connect"), message("Choose an option", "bot")], "mode": "diagnose"}).json()
    assert "1. Check" in result["reply"] and "Wi-Fi" in result["reply"]
    assert result["offer_options"]


def test_diagnosis_does_not_bypass_fixed_topics(client):
    result = client.post("/api/chat", json={"messages": [message("What is my ticket status?")], "mode": "diagnose"}).json()
    assert result["escalation_reason"] == "fixed_topic"
    assert "cannot" in result["reply"]


def test_no_history_leaks_between_requests(client):
    client.post("/api/chat", json={"messages": [message("Wi-Fi won't connect")]})
    result = client.post("/api/chat", json={"messages": [message("It still does that")]}).json()
    assert result["escalation_reason"] is None and not result["offer_options"]


@pytest.mark.parametrize("text", ["How's the weather today?", "Can you predict the weather?", "Is it raining?", "Tell me a joke", "Give me a recipe", "What's the football score?", "hello", "What is a fingerprint?"])
@pytest.mark.parametrize("mode", ["conversation", "diagnose"])
def test_off_topic_never_offers_ots_email_or_diagnosis(client, text, mode):
    # Check both a new conversation and a change of topic after an IT issue.
    for history in ([], [message("I reset my password"), message("It still won't let me in")]):
        result = client.post("/api/chat", json={"messages": history + [message(text)], "mode": mode}).json()
        assert result["offer_options"] is False
        assert result["escalate"] is False and result["escalation_reason"] is None
        assert "OTS technology questions" in result["reply"]


@pytest.mark.parametrize("text", ["My weather app won't load", "My Wi-Fi will not connect", "My Bluetooth mouse is not working", "My printer is broken"])
def test_actual_technical_problems_remain_in_scope(client, text):
    result = client.post("/api/chat", json={"messages": [message(text)]}).json()
    assert result["offer_options"] is True


def test_draft_uses_user_words_and_redacts_common_identifiers(client):
    result = client.post("/api/escalate", json={"messages": [
        message("My Wi-Fi fails on a laptop and my email is student@example.test A12345678"),
        message("The issue is resolved and a ticket was filed", "bot"),
    ]}).json()
    body = result["email"]["body"]
    assert "student@example.test" not in body and "A12345678" not in body
    assert "resolved" not in body and "ticket was filed" not in body


@pytest.mark.parametrize("payload", [
    {"messages": []},
    {"messages": [message("   ")]},
    {"messages": [message("x" * 4001)]},
    {"messages": [message("hello", "system")]},
    {"messages": [message("hello", "bot")]},
    {"messages": [message("hello")] * 61},
    {"messages": [message("x" * 4000)] * 7},
    {"messages": [message("hello")], "student_id": "A12345678"},
])
def test_bad_input_is_rejected_without_echo(client, payload):
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
    assert "A12345678" not in response.text and "input" not in response.json()


def test_dependency_failure_has_recoverable_error_without_details():
    class Broken(DemoService):
        def chat(self, request):
            raise RuntimeError("sensitive internal exception")

        def escalate(self, request):
            raise TimeoutError("sensitive internal exception")

    with TestClient(create_app(Broken())) as client:
        for route in ("/api/chat", "/api/escalate"):
            result = client.post(route, json={"messages": [message("test")]})
            assert result.status_code == 503 and "try again" in result.json()["detail"]
            assert "sensitive" not in result.text


def test_cors_allows_only_configured_local_origins(client):
    headers = {"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"}
    assert client.options("/api/chat", headers=headers).headers["access-control-allow-origin"] == headers["Origin"]
    headers["Origin"] = "https://example.com"
    assert "access-control-allow-origin" not in client.options("/api/chat", headers=headers).headers
