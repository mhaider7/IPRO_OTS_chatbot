from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from api.main import create_app
from escalation.delivery import GraphDelivery, MailSettings


@pytest.fixture
def settings(tmp_path):
    return MailSettings(enabled=True, tenant=str(uuid4()), client=str(uuid4()), secret="test-secret", mailbox="hawk@example.test", recipient="ots@example.test", ledger=tmp_path / "ledger.sqlite3")


def payload():
    return {"request_id": str(uuid4()), "reply_to": "student@example.test", "subject": "Wi-Fi issue", "body": "The fictional laptop cannot connect.", "confirmed": True}


def client_for(settings, handler):
    return TestClient(create_app(delivery=GraphDelivery(settings, httpx.MockTransport(handler))))


def test_graph_contract_and_persistent_deduplication(settings):
    calls = []
    def handler(request):
        calls.append(request)
        if "oauth2" in str(request.url):
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.headers["authorization"] == "Bearer test-token"
        assert str(request.url).endswith("hawk%40example.test/sendMail")
        message = json.loads(request.content)
        assert message["message"]["toRecipients"][0]["emailAddress"]["address"] == "ots@example.test"
        assert message["message"]["replyTo"][0]["emailAddress"]["address"] == "student@example.test"
        assert message["message"]["body"]["contentType"] == "Text"
        assert message["saveToSentItems"] is True
        return httpx.Response(202)
    data = payload()
    with client_for(settings, handler) as client:
        assert client.get("/api/email/status").json() == {"available": True, "recipient": "ots@example.test"}
        assert client.post("/api/email/send", json=data).json() == {"status": "accepted"}
    with client_for(settings, handler) as restarted:
        assert restarted.post("/api/email/send", json=data).json() == {"status": "accepted"}
        assert restarted.post("/api/email/send", json={**data, "body": "different"}).status_code == 409
    assert len(calls) == 2
    with sqlite3.connect(settings.ledger) as db:
        saved = str(db.execute("SELECT * FROM sends").fetchall())
        assert "student@" not in saved and "fictional laptop" not in saved and "test-secret" not in saved


@pytest.mark.parametrize("failure", ["timeout", "server_error", "unauthorized", "token_error"])
def test_failures_never_report_sent_and_ambiguous_attempts_do_not_resend(settings, failure):
    submissions = []
    def handler(request):
        if "oauth2" in str(request.url):
            return httpx.Response(401) if failure == "token_error" else httpx.Response(200, json={"access_token": "test"})
        submissions.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("provider diagnostic should not leak")
        return httpx.Response(500 if failure == "server_error" else 403)
    data = payload()
    expected = "unknown" if failure in {"timeout", "server_error"} else "failed"
    with client_for(settings, handler) as client:
        for _ in range(2):
            response = client.post("/api/email/send", json=data)
            assert response.json() == {"status": expected}
            assert "diagnostic" not in response.text
    assert len(submissions) == (0 if failure == "token_error" else 1)


def test_disabled_sender_never_calls_provider(settings):
    def unexpected(request):
        pytest.fail("Must not call Microsoft when disabled")
    with client_for(replace(settings, enabled=False), unexpected) as client:
        assert client.get("/api/email/status").json()["available"] is False
        assert client.post("/api/email/send", json=payload()).status_code == 503


@pytest.mark.parametrize("changes", [{"confirmed": False}, {"reply_to": "not an email"}, {"subject": "hello\r\nBcc: evil@example.test"}, {"to": "evil@example.test"}, {"body": " "}])
def test_validation_prevents_unconfirmed_or_retargeted_send(settings, changes):
    with client_for(settings, lambda request: pytest.fail("No provider call expected")) as client:
        assert client.post("/api/email/send", json={**payload(), **changes}).status_code == 422


def test_untrusted_origin_is_blocked(settings):
    with client_for(settings, lambda request: pytest.fail("No provider call expected")) as client:
        assert client.post("/api/email/send", json=payload(), headers={"Origin": "https://evil.example"}).status_code == 403


def test_concurrent_duplicate_requests_send_once(settings):
    submissions = []
    def handler(request):
        if "oauth2" in str(request.url):
            return httpx.Response(200, json={"access_token": "test"})
        submissions.append(request)
        return httpx.Response(202)
    with client_for(settings, handler) as client:
        data = payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post("/api/email/send", json=data), range(2)))
        assert all(result.json()["status"] in {"accepted", "unknown"} for result in results)
        assert len(submissions) == 1
