import json

import httpx
import pytest

from api.schemas import Message
from llm import ollama_client
from llm.confidence import grade, parse_confidence
from llm.memory import recent_history, retrieval_query, to_ollama
from llm.prompts import format_context
from retrieval.retriever import Chunk


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chat_returns_text_and_sends_model_options():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": " Restart Wi-Fi. "}})

    assert ollama_client.chat([{"role": "user", "content": "hi"}], client=client(handler)) == "Restart Wi-Fi."
    assert seen["stream"] is False and seen["options"]["num_ctx"] == 8192


@pytest.mark.parametrize("handler", [
    lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused")),
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    lambda request: httpx.Response(500, text="boom"),
    lambda request: httpx.Response(200, json={"unexpected": True}),
])
def test_unreachable_or_broken_ollama_raises_clear_error(handler):
    with pytest.raises(ollama_client.OllamaUnavailable) as error:
        ollama_client.chat([{"role": "user", "content": "my secret text"}], client=client(handler))
    assert "my secret text" not in str(error.value)


def test_chat_json_rejects_non_json():
    handler = lambda request: httpx.Response(200, json={"message": {"content": "not json"}})
    with pytest.raises(ollama_client.OllamaUnavailable):
        ollama_client.chat_json([], {"type": "object"}, client=client(handler))


@pytest.mark.parametrize("value,expected", [
    ({"confidence": "high"}, "high"), ({"confidence": "Medium"}, "medium"), ({"confidence": "low"}, "low"),
    ({"confidence": "very sure"}, "low"), ({}, "low"), ("high", "high"), (None, "low"),
])
def test_confidence_parsing_defaults_to_low(value, expected):
    assert parse_confidence(value) == expected


def test_grade_sends_material_and_answer():
    chunk = Chunk("Forget the network and reconnect.", "OTS: Wi-Fi", "https://www.iit.edu/ots/x", "ots", 0.2)
    captured = {}

    def fake_json(messages, schema, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return {"confidence": "medium"}

    assert grade("Wi-Fi fails", [chunk], "Forget the network.", chat_json=fake_json) == "medium"
    assert "Forget the network and reconnect." in captured["prompt"] and "OTS: Wi-Fi" in captured["prompt"]


def test_memory_maps_roles_and_builds_followup_query():
    messages = [Message(role="user", text="My laptop won't connect to IIT-Secure"),
                Message(role="bot", text="Try forgetting the network."),
                Message(role="user", text="I tried that and it still fails")]
    assert recent_history(messages) == to_ollama(messages[:2])
    assert recent_history(messages)[1] == {"role": "assistant", "content": "Try forgetting the network."}
    assert retrieval_query(messages) == "My laptop won't connect to IIT-Secure I tried that and it still fails"
    assert retrieval_query(messages[:1]) == messages[0].text


def test_recent_history_is_capped():
    messages = [Message(role="user" if i % 2 == 0 else "bot", text=f"m{i}") for i in range(21)]
    assert len(recent_history(messages, max_turns=8)) == 8


def test_context_labels_chunks_with_sources():
    text = format_context([Chunk("A", "OTS: VPN", None, "ots", 0.1), Chunk("B", "Public IT ticket dataset", None, "ticket", 0.3)])
    assert text.startswith("--- OTS: VPN ---\nA") and "--- Public IT ticket dataset ---\nB" in text and "[1]" not in text
    assert "No matching" in format_context([])


MATERIAL = "OTS: Getting Connected. Select IIT-Secure and enter your Illinois Tech email address and password. Call 312-567-3375."


@pytest.mark.parametrize("answer,expected", [
    ("Select IIT-Secure, then enter your email and password.", []),
    ("1. Ensure Wi-Fi is on.\n2. Check that you picked IIT-Secure.", []),
    ("Call 312-567-3375 or visit portal.iit.edu.", ["portal.iit.edu"]),
    ("Connect to HawkNet with guest code IIT2024.", ["HawkNet", "IIT2024"]),
    ("Install GlobalProtect from vpn.iit.edu/mac and call 312-555-0100.", ["312-555-0100", "GlobalProtect", "vpn.iit.edu/mac"]),
])
def test_unsupported_specifics_catch_invented_details(answer, expected):
    from llm.confidence import unsupported_specifics
    assert unsupported_specifics(answer, MATERIAL, "my PS5 won't connect") == expected


def test_invented_detail_is_low_even_if_model_says_high():
    chunk = Chunk(MATERIAL, "OTS: Getting Connected", None, "ots", 0.2)
    assert grade("wifi", [chunk], "Join HawkNet instead.", chat_json=lambda *a, **k: {"confidence": "high"}) == "low"


def test_grounded_answer_overrules_harsh_self_grade():
    chunk = Chunk(MATERIAL, "OTS: Getting Connected", None, "ots", 0.2)
    answer = "Select IIT-Secure and enter your Illinois Tech email address and password."
    assert grade("wifi", [chunk], answer, chat_json=lambda *a, **k: {"confidence": "low"}) == "medium"
    assert grade("wifi", [chunk], "Restart everything and wait a day.", chat_json=lambda *a, **k: {"confidence": "low"}) == "low"
