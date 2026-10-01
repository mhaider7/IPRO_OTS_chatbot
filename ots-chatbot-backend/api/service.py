"""Swap DemoService for the real retrieval/LLM coordinator at create_app()."""
import re
from typing import Protocol

from api.schemas import ChatRequest, ChatResponse, Conversation, EscalationResponse
from escalation.email_builder import build_test_email
from escalation.topics import HUMAN_REQUEST, fixed_topic, in_support_scope, topic_for


class ChatService(Protocol):
    def chat(self, request: ChatRequest) -> ChatResponse: ...
    def escalate(self, request: Conversation) -> EscalationResponse: ...


class DemoService:
    def chat(self, request: ChatRequest) -> ChatResponse:
        users = [message.text for message in request.messages if message.role == "user"]
        latest = users[-1]
        if not in_support_scope(latest, users):
            return ChatResponse(reply="I can help with Illinois Tech OTS technology questions, such as Wi-Fi, account access, printing, and software. What campus technology issue can I help you with?", offer_options=False)
        reason = None
        if re.search(HUMAN_REQUEST, latest, re.I):
            reason = "user_request"
        elif fixed_topic(latest, users):
            reason = "fixed_topic"
        if reason == "fixed_topic":
            if request.mode == "diagnose":
                return ChatResponse(reply="OTS must check this account-specific issue. Safe preparation steps:\n1. Note the exact error and when it started.\n2. List the standard steps you already tried.\n3. Keep passwords, verification codes, and student IDs out of chat.\nChoose Email OTS when you are ready; Hawk cannot reset your account or retrieve ticket records.", escalate=True, escalation_reason=reason)
            return ChatResponse(reply="This needs OTS to check your account or records. I cannot look those up or change them. Choose Email OTS to explain the issue, or Get troubleshooting steps to check what you can do safely first.", escalate=True, escalation_reason=reason)
        topic = topic_for(latest)
        if not topic and re.search(r"\b(that|it|still|same|phone|tried)\b", latest, re.I):
            topic = next((topic_for(text) for text in reversed(users[:-1]) if topic_for(text)), None)
        if request.mode == "diagnose":
            steps = {
                "Wi-Fi": "1. Check that Wi-Fi is on and airplane mode is off.\n2. Toggle Wi-Fi off and back on, then reconnect to your usual network.\n3. Note the exact error and whether another website or device works. Do not share passwords.\nWhich step failed, and what error do you see?",
                "printing": "1. Check that you selected the intended printer and that it shows as available.\n2. Check the print queue for a paused or stuck job.\n3. Note any error shown before retrying once, to avoid duplicate jobs.\nWhat does the queue or printer show?",
                "VPN": "1. Check whether an ordinary website loads with the VPN disconnected.\n2. Close and reopen your already-installed VPN client.\n3. Note the error without sharing sign-in codes or passwords.\nIs the problem the connection or the sign-in step?",
                "software": "1. Note which application and action produces the problem.\n2. Save your work, then close and reopen the application.\n3. Record the exact error text. Licensing or account changes require OTS.\nWhat error do you see?",
            }
            if topic in steps:
                return ChatResponse(reply=f"General troubleshooting for {topic} (not a verified OTS procedure):\n\n{steps[topic]}")
            return ChatResponse(reply="I do not have verified self-service instructions for this issue yet. Note the device, exact error, and what you have already tried. Do not share credentials or attempt account changes. You can add those details here or choose Email OTS.", escalate=True, escalation_reason=reason or "low_confidence")
        if not topic:
            return ChatResponse(reply="I need more detail to diagnose this issue. You can describe the device and error, choose general troubleshooting, or email OTS for help.", escalate=True, escalation_reason=reason or "low_confidence")
        return ChatResponse(reply=f"I understand this concerns {topic}. How would you like to continue? I can help you work through general checks or prepare an email to OTS.", escalate=reason is not None, escalation_reason=reason)

    def escalate(self, request: Conversation) -> EscalationResponse:
        return build_test_email(request)
