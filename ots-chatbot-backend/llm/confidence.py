"""Confidence: the model's self-grade, checked against what the answer actually says.

llama3.2:3b rejects many correct answers when it grades itself, but invented answers reliably
name something the material does not contain (an app, link, phone number, or code). So:
1. Any unsupported specific detail means "low", whatever the model says.
2. Otherwise the self-grade decides, except that a "low" is overruled when the answer mostly
   repeats the material's own words.
"""
import re
from typing import Literal

from llm import ollama_client
from llm.prompts import CONFIDENCE_PROMPT, CONFIDENCE_SCHEMA, format_context

Confidence = Literal["low", "medium", "high"]
GROUNDED_OVERLAP = 0.5
# Platform names a correct answer may mention without the material spelling them out.
ALLOWED_NAMES = {"ots", "illinois", "tech", "i", "wi-fi", "wifi", "windows", "mac", "macos", "iphone", "ipad",
                 "android", "ios", "support", "desk"}
STOPWORDS = set("""the and for you your with that this from have are can will not but was were has had its into then than
they them their there here what when where which who how why also just only more most some such very would could should
may might must about after before over under again once each other any all both few many much own same too out off our
his her she him he we us me my if else up down please need needs use using make sure click select open go get try tap
enter it's let's""".split())


def parse_confidence(value) -> Confidence:
    """Anything other than a clear medium/high counts as low, so doubt always escalates."""
    if isinstance(value, dict):
        value = value.get("confidence")
    if isinstance(value, str) and value.strip().lower() in {"medium", "high"}:
        return value.strip().lower()  # type: ignore[return-value]
    return "low"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9](?:[a-z0-9'\-]*[a-z0-9])?", text.lower())


def unsupported_specifics(answer: str, material: str, question: str = "") -> list[str]:
    """Links, numbers, codes, and mid-sentence proper names in the answer that the material lacks."""
    known = f"{material} {question}".lower()
    candidates = set()
    candidates |= {m.rstrip(".,;:)!?") for m in re.findall(r"https?://\S+|\b[\w.-]+\.(?:edu|com|org|net|io)\b\S*", answer)}
    candidates |= set(re.findall(r"\b\d[\d\-() x]{3,}\d\b|\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9-]{3,}\b", answer))
    for sentence in re.split(r"(?<=[.!?:])\s+|\n+", answer):
        words = re.sub(r"^\W*(?:\d+[.)]\s*)?", "", sentence).split()
        for word in words[1:]:  # The first word of a sentence is capitalized anyway.
            word = word.strip("\"'“”‘’()[],.;:!?*")
            if re.fullmatch(r"[A-Z][A-Za-z0-9-]{2,}", word):
                candidates.add(word)
    return sorted(c for c in candidates if c and c.lower() not in ALLOWED_NAMES and c.lower() not in known)


def overlap(answer: str, material: str) -> float:
    """Share of the answer's content words that also appear in the material."""
    vocabulary = set(_words(material))
    words = [word for word in _words(answer) if len(word) > 2 and word not in STOPWORDS]
    return sum(word in vocabulary for word in words) / max(1, len(words))


def self_grade(question: str, chunks, answer: str, chat_json=None) -> Confidence:
    prompt = CONFIDENCE_PROMPT.format(context=format_context(chunks), question=question, answer=answer)
    # Temperature 0 so the same answer gets the same grade every time.
    result = (chat_json or ollama_client.chat_json)([{"role": "user", "content": prompt}], CONFIDENCE_SCHEMA, temperature=0)
    return parse_confidence(result)


def grade(question: str, chunks, answer: str, chat_json=None) -> Confidence:
    material = " ".join(chunk if isinstance(chunk, str) else f"{chunk.source} {chunk.text}" for chunk in chunks)
    if unsupported_specifics(answer, material, question):
        return "low"
    rating = self_grade(question, chunks, answer, chat_json)
    if rating == "low" and overlap(answer, material) >= GROUNDED_OVERLAP:
        return "medium"
    return rating
