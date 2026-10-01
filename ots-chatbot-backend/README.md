# Hawk API and connected demo

Hawk now offers two paths after an issue is described: **Email OTS** or **Get troubleshooting steps**. Email is reviewed and explicitly submitted inside Hawk through Microsoft 365. This implements the October 1 change from copy/paste. Guidance is currently deterministic general troubleshooting; ChromaDB, verified OTS procedures, model confidence grading, and Ollama are not connected yet.

## Run locally

From the repository root with Python 3.11 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ots-chatbot-backend/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir ots-chatbot-backend --host 127.0.0.1 --port 8000
```

On macOS/Linux use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

Open <http://127.0.0.1:8000/> for the connected Hawk demo and <http://127.0.0.1:8000/docs> for the API. The app serves its own frontend, so no frontend build or separate web server is required. Stop any other service using port 8000 first, or select another port.

The runnable frontend is `IIT_Chatbot_UI_Design/index.html`, `hawk.css`, and `hawk.js`. It adapts the existing OTS/Hawk design into ordinary browser code. The `.dc.html` file and its `support.js` runtime are preserved as the original design reference; open the server URL above to use the connected version.

## Try the complete flow

1. Click **Ask Hawk** and send **My Wi-Fi will not connect**. Two choices appear; no email is prepared or sent automatically.
2. Choose **Get troubleshooting steps**. Follow the general checks and describe the result. Hawk retains the topic from recent history.
3. Choose **Email OTS** at any point after describing the issue. Answer the optional clarifying question, review/edit the message, and enter the address OTS should reply to.
4. With Microsoft 365 configured, check the confirmation box and choose **Send email to OTS**. Without configuration, the button is disabled with an explanation.
5. Try **What is my ticket status?**. Self-service explains that only OTS can look up the record; choosing it never bypasses that restriction. Unrecognized issues also offer both choices without inventing a diagnosis.

The no-match fixture uses the contract's `low_confidence` reason to exercise that UI path; it is not a real model confidence assessment. Topic checks are example rules rather than a complete production classifier.

The scope gate distinguishes unrecognized technical issues from unrelated questions. For example, "How's the weather today?" gets an OTS-scope reminder with `offer_options: false` and no escalation. "My weather app won't load" remains a technical issue. A change of topic does not inherit a previous account or Wi-Fi issue. These rules are conservative prototype routing, not a general-purpose language understanding model.

## API contract

Chat and escalation accept `{ "messages": [{ "role": "user", "text": "My Wi-Fi fails" }] }`. Chat also accepts `mode: "conversation"` (default) or `mode: "diagnose"`. Normal chat must end with a user message; diagnosis may follow a bot reply because choosing a button adds no invented student text. The frontend stays on `/api/escalate` while collecting email clarification and allows switching back to diagnosis.

| Route | Response |
| --- | --- |
| `GET /api/health` | `{ "status": "ok" }` |
| `POST /api/chat` | `{ "reply": "...", "sources": [], "escalate": false, "escalation_reason": null, "offer_options": true }` |
| `POST /api/escalate` | `{ "email": { "to": "...", "subject": "...", "body": "..." }, "clarifying_question": null }` or `{ "email": null, "clarifying_question": "..." }` |
| `GET /api/email/status` | `{ "available": false, "recipient": "supportdesk@illinoistech.edu" }` |
| `POST /api/email/send` | `{ "status": "accepted" }`, `failed`, or `unknown` |

The send request contains `request_id` (UUID), `reply_to`, `subject`, `body`, and `confirmed: true`. Recipients and sender are server-configured, never supplied by the browser. `escalate` remains a recommendation signal for compatibility; it no longer automatically forces the email path. Both options are shown when `offer_options` is true.

An escalating chat response uses `fixed_topic`, `low_confidence`, or `user_request` as its reason. Invalid requests return HTTP 422; unavailable dependencies return HTTP 503 with a short `detail` message. Inputs are limited to 60 messages, 4,000 characters per message, and 24,000 total characters. Error replies do not echo request content.

The default UI calls the API on its own origin. For a separate local frontend, set `HAWK_ALLOWED_ORIGINS` to comma-separated exact origins before starting the server; localhost and 127.0.0.1 on port 8000 are allowed by default. CORS is not authentication.

## Team integration points

- **Part 4:** `api/main.py` owns routes and frontend serving; `api/schemas.py` owns request/response validation.
- **Parts 2 and 3:** Replace `DemoService.chat()` via the `ChatService` interface in `api/service.py` with retrieval, grounded generation, and confidence decisions. `create_app(service=...)` accepts the replacement for integration and testing. Put real retrieval and LLM code in the guide's `retrieval/` and `llm/` directories when those parts are ready.
- **Part 5:** Replace `escalation/email_builder.py` through `ChatService.escalate()`. Preserve the exclusive email-or-question response shape. `escalation/topics.py` is the shared location for the current test rules.
- **Part 6:** `tests/test_api.py` checks conversation contracts; `tests/test_delivery.py` mocks Microsoft Graph to check sending and deduplication; `tests/browser_options.cjs` exercises both UI paths without sending real mail.

Map frontend role `bot`/field `text` to Ollama role `assistant`/field `content` inside the future model adapter. Keep the public API stable. A real model adapter must enforce its own request timeout; the browser already aborts after 15 seconds and provides retry. Real generation may require an agreed longer timeout or a streaming contract later.

## Data handling

Use fictional issues for development. Chat content stays in page/process memory and is not logged or persisted by Hawk. Closing the widget retains it; **New chat** or reload clears it. Email review intentionally collects a reply address. Confirming send shares that address and the reviewed body with Microsoft 365 and OTS. Microsoft retains sent mail according to the mailbox's policies. Hawk's SQLite delivery ledger stores only a random request ID, a payload hash, status, and timestamp, never email/body/address content. Keep the ledger to preserve duplicate-send protection across restarts.

The template masks common email addresses, A-number student IDs, and explicitly labeled password/code fields if accidentally typed. This is a limited safeguard, not comprehensive personal-data detection. Use de-identified test conversations; real data and public deployment need further review.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest ots-chatbot-backend/tests -q
```

For browser checks, install Playwright in a local development environment, start the server, and run:

```powershell
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node ots-chatbot-backend/tests/browser_options.cjs
```

If Microsoft Edge is already installed, set `$env:HAWK_BROWSER_CHANNEL='msedge'` to use it instead of downloading Chromium. `HAWK_BASE_URL` overrides the default server URL. Screenshots go into ignored `ots-chatbot-backend/.browser-output/`, or the directory set in `HAWK_SCREENSHOT_DIR`.

The browser check covers both choices, general steps, account restrictions, review/confirmation, unavailable configuration, simulated provider acceptance and uncertain outcomes, same-ID retry, chat failure/retry, mobile widths, and clearing history on reload. Browser delivery responses and Python provider calls are mocked; these tests do not send real email.

## Microsoft 365 setup

Sending is disabled by default. Ask the team's Microsoft 365 administrator for an approved sending mailbox and a Microsoft Entra app with **Microsoft Graph application Mail.Send** permission and administrator consent. Ask the administrator to restrict mailbox access to the intended sender. The server uses application credentials so students do not have to sign in. A personal Outlook account alone does not supply this tenant/app setup.

Copy `.env.example` to a local ignored `.env`, populate the tenant ID, client ID, client secret, and mailbox through a secure local editor, and set `HAWK_EMAIL_ENABLED=true` only when approved. Never commit credentials or put them in frontend code. Start with `--env-file .env` appended to the uvicorn command above. For the first authorized test use `HAWK_OTS_EMAIL` with a team-controlled mailbox, then configure the real OTS address. Do not test real delivery against the support desk without permission.

For another port, include its exact browser origin in `HAWK_ALLOWED_ORIGINS`. Sending is restricted to loopback clients, checks browser origins, and is capped at 20 attempts per hour in this local milestone. Public deployment needs authentication and appropriate abuse controls before relaxing that restriction.

The sender uses the [Microsoft Graph sendMail API](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0) with the [client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow). Graph's `202` means accepted for processing, not confirmed inbox delivery; the UI says so. Explicit provider rejection is `failed`. A send timeout, server error, or interrupted process is `unknown`: check the sender's Sent Items before another attempt. Repeating the same request ID checks the saved result without sending again. The browser freezes the reviewed payload for retries. A new attempt is offered only after a known failure; do not clear the ledger to retry uncertain sends.
