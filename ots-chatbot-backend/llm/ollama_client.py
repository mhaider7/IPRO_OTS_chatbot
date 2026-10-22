"""Thin client for the local Ollama server, shared by answering, grading, and email drafting."""
import json
import os
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OLLAMA_URL = os.getenv("HAWK_OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
MODEL = os.getenv("HAWK_OLLAMA_MODEL", "llama3.2:3b")
# Ollama defaults to a much smaller window than the model supports. The schema's
# 24,000-character conversation cap is ~6k tokens; this leaves headroom for the
# system prompt, retrieved chunks, and the model's own reply.
NUM_CTX = 8192
# Each call stays well under the browser's 60-second request limit in hawk.js.
TIMEOUT = float(os.getenv("HAWK_OLLAMA_TIMEOUT", "25"))


class OllamaUnavailable(RuntimeError):
    """Ollama is not running, timed out, or returned something unusable."""


def chat(messages: list[dict], *, format: dict | str | None = None, timeout: float = TIMEOUT,
         temperature: float = 0.2, client: httpx.Client | None = None) -> str:
    payload = {"model": MODEL, "messages": messages, "stream": False, "options": {"num_ctx": NUM_CTX, "temperature": temperature}}
    if format is not None:
        payload["format"] = format
    try:
        response = (client or httpx).post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        # Never include the conversation in the error; it may hold student text.
        raise OllamaUnavailable(f"Ollama request failed: {type(exc).__name__}") from exc


def chat_json(messages: list[dict], schema: dict, **kwargs) -> dict:
    """Structured output: Ollama constrains the reply to the JSON schema."""
    text = chat(messages, format=schema, **kwargs)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OllamaUnavailable("Ollama returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise OllamaUnavailable("Ollama returned an unexpected JSON shape")
    return value


def generate_answer(question: str, context_chunks: list[str], history: list[dict] | None = None) -> str:
    """history holds prior turns only (role/text pairs), not the current question."""
    from llm.memory import to_ollama
    from llm.prompts import answer_system_prompt

    return chat([
        {"role": "system", "content": answer_system_prompt(context_chunks)},
        *to_ollama(history or []),
        {"role": "user", "content": question},
    ])


if __name__ == "__main__":
    from retrieval.retriever import retrieve

    history = []
    for question in [
        "My laptop won't connect to the campus Wi-Fi",
        "I tried that, it still won't connect even after restarting",
    ]:
        chunks = retrieve(question)
        answer = generate_answer(question, [chunk.text for chunk in chunks], history)
        print(f"Question: {question}\n")
        print(f"Retrieved {len(chunks)} chunk(s) as grounding context.\n")
        print(f"Answer:\n{answer}\n{'-' * 40}")
        history.append({"role": "user", "text": question})
        history.append({"role": "bot", "text": answer})
