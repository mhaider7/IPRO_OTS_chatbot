# Hawk backend plan

This is a repository summary of the team's agreed `OTS_Chatbot_Backend_Guide.pdf`. The PDF is the source for the full six-part assignment and detailed acceptance criteria. The final section records which integration milestone is currently implemented.

**October 1 update:** The user confirmed Microsoft 365/Outlook and requested two conversation choices, removal of the standalone technician button, and sending email inside Hawk. These changes supersede the original guide's copy/paste-only restriction. Sending requires an approved app/mailbox configuration; this repository does not provision university accounts or permissions.

## Student flow for this version

1. A student asks Hawk a question. The frontend sends the conversation so far to `POST /api/chat`.
2. The backend checks topics that always need a person before searching for an answer.
3. For other questions, it retrieves relevant, source-labeled OTS material from a local ChromaDB index and asks a local Ollama model to answer using that material and recent conversation context.
4. Hawk offers **Email OTS** and **Get troubleshooting steps** after receiving an issue. Account-specific requests remain limited to safe preparation steps and an OTS referral. Choosing self-service does not grant access to account records.
5. In the email path, Hawk may ask a clarifying question, then prepares a message. The student reviews it, supplies a reply address, and explicitly confirms sending through Microsoft 365. The student can switch paths before sending.

There is no student login or TeamDynamix ticket API. The intentional reply-address field is a change to the original no-personal-data scope. That address and the reviewed message are transmitted to Microsoft 365 only upon confirmation; mail remains subject to the sending mailbox's retention settings. Hawk does not persist conversation or message content.

## Frontend API contract

| Route | Request | Response |
| --- | --- | --- |
| `POST /api/chat` | Full conversation as `messages`, plus `mode` (`conversation` or `diagnose`) | `reply`, `sources`, `escalate`, `escalation_reason`, `offer_options` |
| `POST /api/escalate` | Full conversation as `messages` | An `email` object (`to`, `subject`, `body`) or a `clarifying_question` |
| `GET /api/health` | No body | `{ "status": "ok" }` |
| `GET /api/email/status` | No body | Configuration availability and fixed recipient |
| `POST /api/email/send` | Unique request ID, reply address, reviewed subject/body, explicit confirmation | `accepted`, `failed`, or `unknown` |

The guide defines escalation reasons as `fixed_topic`, `low_confidence`, and `user_request`. Keep the frontend and backend contract in sync if the team changes it.

## Planned backend pieces

- Clean and de-identify source material, split it into chunks, label sources, and build a local ChromaDB index.
- Implement fixed-topic checks, retrieval, and a confidence decision. A missing or poor evidence match should not produce a confident answer.
- Integrate a local Ollama model for grounded answers and short conversation context.
- Maintain the FastAPI routes above, with browser access for local frontend testing.
- Generate a reviewable support email, ask for essential missing details, and submit only after the student's confirmation.
- Connect the existing Hawk widget to the API and test ordinary answers, follow-ups, and all escalation triggers end to end.

## Current repository state

The connected demo is implemented in [`ots-chatbot-backend/`](ots-chatbot-backend/README.md) and `IIT_Chatbot_UI_Design/index.html`. It offers both conversation paths, labeled general checks, one optional email clarification, and an editable email review with confirmation. The backend has Microsoft Graph delivery and a persistent duplicate-send ledger. Live delivery still needs the team's approved application/mailbox setup. The original `.dc.html` file is a historical design reference; use the server URL for the current UI.

The service uses deterministic general guidance and a template-based email summary. Verified source ingestion, ChromaDB retrieval, Ollama generation, real confidence checks, and model-generated email summaries are not implemented yet. These are the next backend integration steps behind the existing contract.

The team removed the earlier ticket sandbox from main; the current branch starts from that updated main.
