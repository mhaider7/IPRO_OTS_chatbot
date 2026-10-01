"""Microsoft Graph delivery with a persistent, content-free duplicate-send ledger."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote
from uuid import UUID

import httpx

from api.schemas import Address, SendEmailRequest
from pydantic import TypeAdapter


class DeliveryError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


@dataclass(frozen=True)
class MailSettings:
    enabled: bool = False
    tenant: str = ""
    client: str = ""
    secret: str = ""
    mailbox: str = ""
    recipient: str = "supportdesk@illinoistech.edu"
    ledger: Path = Path(__file__).resolve().parents[1] / ".runtime" / "email.sqlite3"

    @classmethod
    def from_env(cls):
        return cls(
            enabled=os.getenv("HAWK_EMAIL_ENABLED", "false").lower() == "true",
            tenant=os.getenv("HAWK_MS_TENANT_ID", ""), client=os.getenv("HAWK_MS_CLIENT_ID", ""),
            secret=os.getenv("HAWK_MS_CLIENT_SECRET", ""), mailbox=os.getenv("HAWK_MS_MAILBOX", ""),
            recipient=os.getenv("HAWK_OTS_EMAIL", "supportdesk@illinoistech.edu"),
            ledger=Path(os.getenv("HAWK_EMAIL_LEDGER", str(cls.ledger))),
        )

    @property
    def ready(self):
        if not self.enabled or not self.secret:
            return False
        try:
            UUID(self.tenant); UUID(self.client)
            for address in (self.mailbox, self.recipient):
                TypeAdapter(Address).validate_python(address)
            return True
        except (ValueError, TypeError):
            return False


class GraphDelivery:
    def __init__(self, settings: MailSettings, transport: httpx.BaseTransport | None = None):
        self.settings, self.transport = settings, transport

    def connection(self):
        self.settings.ledger.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.settings.ledger, timeout=10)
        connection.execute("CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL)")
        return connection

    def result(self, state: str):
        return {"status": state}

    def send(self, request: SendEmailRequest):
        if not self.settings.ready:
            raise DeliveryError(503, "Microsoft 365 sending is not configured. No new email was submitted by this request.")
        request_id = str(request.request_id)
        content = request.model_dump_json() + self.settings.recipient + self.settings.mailbox
        fingerprint = hashlib.sha256(content.encode()).hexdigest()
        connection = self.connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT fingerprint, state FROM sends WHERE id=?", (request_id,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise DeliveryError(409, "This send attempt already belongs to a different message.")
                return self.result(row[1])
            recent = connection.execute("SELECT count(*) FROM sends WHERE created>?", (time.time() - 3600,)).fetchone()[0]
            if recent >= 20:
                raise DeliveryError(429, "The local demo's hourly email limit has been reached. Your email has not been sent.")
            # Reserve before calling Graph. A crash leaves 'unknown', never a resend.
            connection.execute("INSERT INTO sends VALUES (?, ?, 'unknown', ?)", (request_id, fingerprint, time.time()))
            connection.commit()
        finally:
            connection.close()

        state = "failed"
        try:
            with httpx.Client(timeout=10, transport=self.transport, follow_redirects=False) as client:
                token = client.post(f"https://login.microsoftonline.com/{self.settings.tenant}/oauth2/v2.0/token", data={
                    "client_id": self.settings.client, "client_secret": self.settings.secret,
                    "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
                })
                token.raise_for_status()
                access_token = token.json()["access_token"]
                if not isinstance(access_token, str) or not access_token:
                    raise ValueError("Invalid token response")
                # Once submitting starts, network/5xx outcomes are ambiguous.
                state = "unknown"
                response = client.post(f"https://graph.microsoft.com/v1.0/users/{quote(self.settings.mailbox, safe='')}/sendMail", headers={
                    "Authorization": f"Bearer {access_token}", "client-request-id": request_id,
                }, json={"message": {
                    "subject": request.subject,
                    "body": {"contentType": "Text", "content": request.body},
                    "toRecipients": [{"emailAddress": {"address": self.settings.recipient}}],
                    "replyTo": [{"emailAddress": {"address": request.reply_to}}],
                }, "saveToSentItems": True})
                if response.status_code == 202:
                    state = "accepted"
                elif 400 <= response.status_code < 500:
                    state = "failed"
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # Provider errors may contain secrets or user content; never return/log them.
        finally:
            with self.connection() as connection:
                connection.execute("UPDATE sends SET state=? WHERE id=?", (state, request_id))
        return self.result(state)
