"""Opt-in end-to-end check against a running Ollama: pytest -m ollama."""
import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.rag_service import RagService
from embeddings.build_index import DB_PATH
from llm.ollama_client import OLLAMA_URL


def ollama_running() -> bool:
    try:
        return httpx.get(OLLAMA_URL.replace("/api/chat", "/api/tags"), timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not ollama_running(), reason="Ollama is not running"),
    pytest.mark.skipif(not DB_PATH.exists(), reason="Knowledge base not built"),
]


def test_real_wifi_answer_and_email():
    with TestClient(create_app(service=RagService())) as client:
        result = client.post("/api/chat", json={"messages": [{"role": "user", "text": "How do I connect my laptop to IIT-Secure Wi-Fi?"}]}).json()
        assert result["reply"]
        if not result["escalate"]:
            assert any("iit.edu/ots" in source for source in result["sources"])
        draft = client.post("/api/escalate", json={"messages": [{"role": "user", "text": "My MacBook will not join IIT-Secure in the library; it says authentication failed."}]}).json()
        assert draft["email"] or draft["clarifying_question"]
