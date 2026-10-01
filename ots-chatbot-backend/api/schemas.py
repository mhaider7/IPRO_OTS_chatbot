from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing_extensions import Annotated
from uuid import UUID

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "bot"]
    text: Text


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[Message] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def limit_history(self):
        if sum(len(message.text) for message in self.messages) > 24000:
            raise ValueError("Conversation is too long. Start a new conversation.")
        return self


class ChatRequest(Conversation):
    mode: Literal["conversation", "diagnose"] = "conversation"
    @model_validator(mode="after")
    def latest_is_user(self):
        if not any(m.role == "user" for m in self.messages) or (self.mode == "conversation" and self.messages[-1].role != "user"):
            raise ValueError("A chat request must end with a student message.")
        return self


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = Field(default_factory=list)
    escalate: bool = False
    escalation_reason: Literal["fixed_topic", "low_confidence", "user_request"] | None = None
    offer_options: bool = True

    @model_validator(mode="after")
    def consistent_reason(self):
        if self.escalate != (self.escalation_reason is not None):
            raise ValueError("Escalation and reason must agree.")
        return self


class EmailDraft(BaseModel):
    to: str
    subject: str
    body: str


class EscalationResponse(BaseModel):
    email: EmailDraft | None = None
    clarifying_question: str | None = None

    @model_validator(mode="after")
    def exactly_one_result(self):
        if (self.email is None) == (self.clarifying_question is None):
            raise ValueError("Return either an email or a clarifying question.")
        return self


Address = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$")]


class SendEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    reply_to: Address
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\r\n]+$")]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24000)]
    confirmed: Literal[True]
