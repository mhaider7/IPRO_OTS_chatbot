# IPRO Ticketing System Automation

This IPRO project is building Hawk, a student-facing OTS support chatbot. After a student describes an issue, Hawk offers two choices: get troubleshooting steps or email OTS. The student can review the email and confirm sending directly from Hawk through an approved Microsoft 365 mailbox. This reflects the October 1 scope update to the original backend guide.

## Repository contents

- [`IIT_Chatbot_UI_Design/`](IIT_Chatbot_UI_Design/) contains the connected Hawk browser interface and the original design reference.
- [`ots-chatbot-backend/`](ots-chatbot-backend/README.md) contains the working API, general troubleshooting flow, and Microsoft Graph email integration. Follow its README to run locally and configure the sending account.
- [`HAWK_BACKEND_PLAN.md`](HAWK_BACKEND_PLAN.md) summarizes the agreed chatbot backend scope, API contract, and next integration milestone.

Sending requires a configured, approved Microsoft 365 application and mailbox. Without that configuration the UI explains that sending is unavailable. Students provide a reply email address only on the review screen and explicitly confirm the submission. Answers come from a local retrieval pipeline: public OTS pages and public IT-support datasets indexed in ChromaDB, a local Ollama model that answers only from that material, and a self-graded confidence check that escalates uncertain answers. Email drafts get a model-written subject and summary, followed by the student's own messages quoted word for word. See the backend README for building the index and installing the model. The former ticket sandbox has been removed from main.
