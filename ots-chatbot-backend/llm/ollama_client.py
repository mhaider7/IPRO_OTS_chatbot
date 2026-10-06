"""Local Ollama integration: an LLM that answers only from retrieved OTS material."""
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2:3b"
SYSTEM_PROMPT = (Path(__file__).resolve().parent / "system_prompt.txt").read_text().strip()
# Ollama defaults to a much smaller window than the model supports. The schema's
# 24,000-character conversation cap is ~6k tokens; this leaves headroom for the
# system prompt, retrieved chunks, and the model's own reply.
NUM_CTX = 8192


ROLE_MAP = {"user": "user", "bot": "assistant"}


def generate_answer(question: str, context_chunks: list[str], history: list[dict] | None = None) -> str:
    """history holds prior turns only (role/text pairs), not the current question."""
    context = "\n\n".join(context_chunks) or "[No matching OTS material was found.]"
    turns = [{"role": ROLE_MAP[turn["role"]], "content": turn["text"]} for turn in history or []]
    response = httpx.post(OLLAMA_URL, json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nOTS material:\n{context}"},
            *turns,
            {"role": "user", "content": question},
        ],
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
    }, timeout=120)
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


if __name__ == "__main__":
    from retrieval.chroma_setup import retrieve

    history = []
    for question in [
        "My laptop won't connect to the campus Wi-Fi",
        "I tried that, it still won't connect even after restarting",
    ]:
        chunks = retrieve(question)
        answer = generate_answer(question, chunks, history)
        print(f"Question: {question}\n")
        print(f"Retrieved {len(chunks)} chunk(s) as grounding context.\n")
        print(f"Answer:\n{answer}\n{'-' * 40}")
        history.append({"role": "user", "text": question})
        history.append({"role": "bot", "text": answer})
