"""Retrieval-augmented ChatService: fixed topics, ChromaDB search, Ollama answer, self-grade."""
import logging
import re

from api.schemas import ChatRequest, ChatResponse, Conversation, EscalationResponse
from api.service import DemoService
from escalation.email_builder import draft_email
from llm import confidence, ollama_client
from llm.memory import recent_history, retrieval_query
from llm.prompts import answer_system_prompt
from retrieval import retriever
from retrieval.topics import HUMAN_REQUEST, UNRELATED, in_support_scope, is_fixed_topic

logger = logging.getLogger("hawk")

NO_MATCH = ("I could not find OTS instructions that match this issue, so I do not want to guess. "
            "Note the device, the exact error, and what you have already tried. You can add those details here or choose Email OTS.")
LOW_CONFIDENCE = ("I am not confident the OTS material I found answers this correctly. "
                  "To avoid giving you wrong steps, choose Email OTS, or add more detail such as the device and exact error.")
MODEL_DOWN = ("Hawk's answer engine is not available right now. You can still choose Email OTS to send your question "
              "to the support desk, or try again in a moment.")
DIAGNOSE_REQUEST = "Please give me troubleshooting steps for the issue I described."


class RagService:
    def __init__(self, retrieve=None, chat=None, chat_json=None, fallback=None):
        self.retrieve = retrieve or retriever.retrieve
        self.chat_fn = chat or ollama_client.chat
        self.chat_json = chat_json or ollama_client.chat_json
        # Scope, fixed-topic, and human-request replies stay identical to the demo's reviewed wording.
        self.fallback = fallback or DemoService()

    def chat(self, request: ChatRequest) -> ChatResponse:
        users = [message.text for message in request.messages if message.role == "user"]
        latest = users[-1]
        if re.search(HUMAN_REQUEST, latest, re.I) or is_fixed_topic(latest, users):
            return self.fallback.chat(request)
        try:
            chunks = self.retrieve(retrieval_query(request.messages))
        except retriever.IndexMissing:
            logger.warning("knowledge base missing; using demo responses")
            return self.fallback.chat(request)
        good = [chunk for chunk in chunks if retriever.is_good(chunk)]
        # The regex gate misses many real issues; a close OTS match also counts as in scope.
        if not in_support_scope(latest, users) and (not good or re.search(UNRELATED, latest, re.I)):
            return self.fallback.chat(request)
        if not good:
            return ChatResponse(reply=NO_MATCH, escalate=True, escalation_reason="low_confidence")

        diagnose = request.mode == "diagnose"
        history = recent_history(request.messages)
        # A button choice adds no student text, so the request ends with Hawk's message.
        question = latest if request.messages[-1].role == "user" else DIAGNOSE_REQUEST
        try:
            answer = self.chat_fn([
                {"role": "system", "content": answer_system_prompt(good, diagnose=diagnose)},
                *history,
                {"role": "user", "content": question},
            ])
            rating = confidence.grade(latest, good, answer, chat_json=self.chat_json)
        except ollama_client.OllamaUnavailable:
            logger.warning("ollama unavailable")
            return ChatResponse(reply=MODEL_DOWN, escalate=True, escalation_reason="low_confidence")
        if rating == "low" or not answer:
            return ChatResponse(reply=LOW_CONFIDENCE, escalate=True, escalation_reason="low_confidence")
        return ChatResponse(reply=answer, sources=retriever.source_labels(good))

    def escalate(self, request: Conversation) -> EscalationResponse:
        users = [message.text for message in request.messages if message.role == "user"]
        reason = None
        if any(re.search(HUMAN_REQUEST, text, re.I) for text in users):
            reason = "user_request"
        elif users and is_fixed_topic(users[-1], users):
            reason = "fixed_topic"
        return draft_email(request, reason, chat_json=self.chat_json)
