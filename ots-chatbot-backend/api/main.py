from pathlib import Path
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import ChatRequest, ChatResponse, Conversation, EscalationResponse, SendEmailRequest
from api.service import ChatService, DemoService
from escalation.delivery import DeliveryError, GraphDelivery, MailSettings

logger = logging.getLogger("hawk")
FRONTEND = Path(__file__).resolve().parents[2] / "IIT_Chatbot_UI_Design"


def create_app(service: ChatService | None = None, delivery: GraphDelivery | None = None) -> FastAPI:
    backend = service or DemoService()
    mail = delivery or GraphDelivery(MailSettings.from_env())
    app = FastAPI(title="Hawk development API", version="0.1.0", description="Deterministic test responses; retrieval and Ollama are not connected.")
    origins = [value.strip() for value in os.getenv("HAWK_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if value.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Avoid echoing the student's input in validation responses or logs.
        return JSONResponse(status_code=422, content={"detail": "Invalid request. Check the message length, required fields, email address, and send confirmation."})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest):
        try:
            result = backend.chat(request)
            logger.info("chat completed: escalate=%s reason=%s", result.escalate, result.escalation_reason)
            return result
        except Exception:
            logger.warning("chat service unavailable")
            return JSONResponse(status_code=503, content={"detail": "Hawk could not respond. Please try again."})

    @app.post("/api/escalate", response_model=EscalationResponse)
    def escalate(request: Conversation):
        try:
            result = backend.escalate(request)
            if result.email:
                result.email.to = mail.settings.recipient
            return result
        except Exception:
            logger.warning("email draft service unavailable")
            return JSONResponse(status_code=503, content={"detail": "Hawk could not prepare the draft. Please try again."})

    @app.get("/api/email/status")
    def email_status():
        return {"available": mail.settings.ready, "recipient": mail.settings.recipient}

    @app.post("/api/email/send")
    def send_email(payload: SendEmailRequest, request: Request):
        # This unauthenticated milestone is local-only. A public deployment needs
        # authenticated/rate-limited sending before removing this restriction.
        if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(status_code=403, content={"detail": "Email sending is available only in the local demo."})
        if request.headers.get("origin") and request.headers["origin"] not in origins:
            return JSONResponse(status_code=403, content={"detail": "This page is not allowed to send email."})
        try:
            return mail.send(payload)
        except DeliveryError as exc:
            return JSONResponse(status_code=exc.status, content={"detail": exc.detail})
        except Exception:
            return JSONResponse(status_code=503, content={"detail": "Email status could not be confirmed. Keep this page open and check the same attempt's status before sending again."})

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")
    return app


app = create_app()
