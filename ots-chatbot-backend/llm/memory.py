"""Conversation memory: the frontend sends the whole chat, so no server-side store is needed."""
import re

ROLE_MAP = {"user": "user", "bot": "assistant"}
FOLLOW_UP = re.compile(r"\b(that|it|this|still|same|again|tried|didn't|did not|doesn't|does not|phone|instead)\b", re.I)


def to_ollama(turns) -> list[dict]:
    """Map frontend role 'bot' / field 'text' to Ollama role 'assistant' / field 'content'."""
    result = []
    for turn in turns:
        role, text = (turn["role"], turn["text"]) if isinstance(turn, dict) else (turn.role, turn.text)
        result.append({"role": ROLE_MAP[role], "content": text})
    return result


def recent_history(messages, max_turns: int = 8) -> list[dict]:
    """Prior turns (excluding the latest student message), capped to the last few exchanges."""
    prior = list(messages)
    if prior and prior[-1].role == "user":
        prior = prior[:-1]
    return to_ollama(prior[-max_turns:])


def retrieval_query(messages) -> str:
    """Search text for the latest question; follow-ups borrow the previous student message."""
    users = [message.text for message in messages if message.role == "user"]
    if not users:
        return ""
    latest = users[-1]
    if len(users) > 1 and (FOLLOW_UP.search(latest) or len(latest.split()) < 6):
        return f"{users[-2]} {latest}"
    return latest
