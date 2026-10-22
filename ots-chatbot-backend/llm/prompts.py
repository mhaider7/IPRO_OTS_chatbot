"""Prompt templates for answering, self-grading, and email drafting."""
from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).resolve().parent / "system_prompt.txt").read_text().strip()

DIAGNOSE_INSTRUCTIONS = (
    "The student chose troubleshooting steps. Reply with at most 5 short numbered steps taken only from the "
    "material, then one question asking which step failed. Never ask for passwords, codes, or student IDs."
)

# Rubric wording chosen by comparing variants against llama3.2:3b on real questions and invented answers.
CONFIDENCE_PROMPT = """Material:
{context}

Question: {question}

Answer: {answer}

Check the answer against the material.
- "high": the material directly covers the question and the answer follows it.
- "medium": the material partly covers the question, or the answer adds small general advice.
- "low": the material is about something else, or the answer contradicts it or invents specific facts.
Reply as JSON: {{"confidence": "low" | "medium" | "high"}}"""

CONFIDENCE_SCHEMA = {
    "type": "object",
    "properties": {"confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
    "required": ["confidence"],
}

# The model writes only the subject and a one-sentence summary; the email body quotes the
# student's own messages, because a small model reliably adds details nobody said.
EMAIL_PROMPT = """A student is emailing the Illinois Tech OTS Support Desk. Read what the student wrote below.

Write:
- "subject": a short subject naming the problem, under 10 words.
- "summary": ONE sentence in first person ("I ...") restating the problem using only facts from the chat.
  Do not add error messages, steps tried, or anything else the student did not say.
{reason_line}
What the student wrote:
{transcript}

Reply as JSON with fields "subject" and "summary"."""

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["subject", "summary"],
}

REASON_LINES = {
    "fixed_topic": "- The issue needs OTS to check the student's account or records.\n",
    "low_confidence": "- Hawk could not find verified self-service steps for this issue.\n",
    "user_request": "- The student asked to reach a person at OTS.\n",
}


def format_context(chunks) -> str:
    """Label each chunk with its source title. No numbers: the model would cite "[2]" to students."""
    if not chunks:
        return "[No matching OTS material was found.]"
    parts = []
    for chunk in chunks:
        text, source = (chunk, None) if isinstance(chunk, str) else (chunk.text, chunk.source)
        parts.append(f"--- {source} ---\n{text}" if source else f"---\n{text}")
    return "\n\n".join(parts)


def answer_system_prompt(chunks, diagnose: bool = False) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\nOTS material:\n{format_context(chunks)}"
    return f"{prompt}\n\n{DIAGNOSE_INSTRUCTIONS}" if diagnose else prompt


def transcript(messages) -> str:
    return "\n".join(f"{'Student' if message.role == 'user' else 'Hawk'}: {message.text}" for message in messages)
