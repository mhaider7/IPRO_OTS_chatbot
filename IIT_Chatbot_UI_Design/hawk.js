/* Conversation survives a reload via sessionStorage (this tab only); no localStorage, cookies, or server-side storage. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const STORAGE_KEY = "hawk-session";
  let history = [], escalating = false, mode = "conversation", busy = false, pending = null, controller = null, epoch = 0, mailSending = false, completed = false;
  let draftNumber = 0;
  const greeting = "Hi, I'm Hawk. What technology problem are you having? Once you describe it, you can choose general troubleshooting or email OTS. Please do not share passwords, verification codes, or student IDs.";

  function save() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ history, escalating, mode, offerOptions: !$("options").hidden, completed }));
    } catch { /* Private browsing or storage disabled; the conversation just will not survive a reload. */ }
  }
  function restore() {
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY)); } catch { return false; }
    if (!saved || !Array.isArray(saved.history) || saved.history.length === 0) return false;
    const validHistory = saved.history.every(m => m && (m.role === "user" || m.role === "bot") && typeof m.text === "string");
    if (!validHistory || (saved.mode !== "conversation" && saved.mode !== "diagnose") || typeof saved.escalating !== "boolean" || typeof saved.completed !== "boolean") return false;
    // A finished chat (advice given, or an email drafted) intentionally does not come back after a reload.
    if (saved.completed) return false;
    history = saved.history; escalating = saved.escalating; mode = saved.mode;
    $("messages").replaceChildren();
    message("bot", greeting);
    for (const turn of history) message(turn.role, turn.text);
    $("chips").hidden = true;
    $("options").hidden = !saved.offerOptions;
    controls();
    return true;
  }

  function message(role, text, sources = []) {
    const row = document.createElement("div");
    row.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    row.append(bubble);
    for (const source of sources) {
      // Never render arbitrary model output as HTML or executable links.
      try {
        const url = new URL(source.startsWith("https://") ? source : `https://${source}`);
        if (url.protocol !== "https:" || !url.hostname.includes(".")) continue;
        const link = document.createElement("a");
        link.className = "source";
        link.href = url.href;
        link.textContent = source;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        row.append(link);
      } catch { /* Ignore unusable source URLs. */ }
    }
    $("messages").append(row);
    scroll();
  }
  function scroll() { $("messages").scrollTop = $("messages").scrollHeight; }
  function controls() {
    for (const id of ["send", "message", "choose-email", "choose-diagnose"]) $(id).disabled = busy || pending !== null || mailSending;
    $("reset").disabled = mailSending;
    for (const chip of document.querySelectorAll("[data-question]")) chip.disabled = busy || pending !== null || mailSending;
    $("retry").disabled = busy;
    $("status").textContent = busy ? "Hawk is responding…" : "";
  }
  async function emailCard(email) {
    const version = epoch;
    // Only one active email draft per conversation; older drafts cannot be sent.
    document.querySelectorAll(".email").forEach(card => card.remove());
    const card = document.createElement("section");
    card.className = "email";
    const heading = document.createElement("h3");
    heading.textContent = "Review your email to OTS";
    const note = document.createElement("p");
    note.textContent = "Check the details below. Hawk will send only this message and your reply address through the configured Microsoft 365 mailbox when you confirm.";
    const to = document.createElement("p");
    to.textContent = `To: ${email.to}`;
    const subject = document.createElement("p");
    subject.textContent = `Subject: ${email.subject}`;
    const label = document.createElement("label");
    const body = document.createElement("textarea");
    body.id = `email-body-${++draftNumber}`;
    body.value = email.body;
    body.maxLength = 24000;
    label.htmlFor = body.id;
    label.textContent = "Review your message";
    const form = document.createElement("form");
    const replyLabel = document.createElement("label");
    const reply = document.createElement("input");
    reply.id = `reply-address-${draftNumber}`; reply.type = "email"; reply.required = true; reply.maxLength = 254;
    replyLabel.htmlFor = reply.id; replyLabel.textContent = "Your email address for OTS replies";
    const confirmLabel = document.createElement("label");
    const confirm = document.createElement("input");
    confirm.type = "checkbox"; confirm.required = true;
    confirmLabel.className = "confirm-send";
    confirmLabel.append(confirm, document.createTextNode(" I reviewed this message and want Hawk to send it to OTS."));
    const sendEmail = document.createElement("button");
    sendEmail.className = "send-email"; sendEmail.type = "submit";
    sendEmail.textContent = "Send email to OTS"; sendEmail.disabled = true;
    const status = document.createElement("span");
    status.className = "delivery-status";
    status.setAttribute("role", "status");
    let payload = null, available = false;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (mailSending || !available || busy || pending || !form.reportValidity()) return;
      if (!body.value.trim()) { status.textContent = "Please enter a message before sending."; return; }
      payload ??= { request_id: crypto.randomUUID(), reply_to: reply.value.trim(), subject: email.subject, body: body.value.trim(), confirmed: true };
      mailSending = true; controls(); sendEmail.disabled = true;
      body.readOnly = true; reply.readOnly = true; confirm.disabled = true;
      status.textContent = "Submitting to Microsoft 365…";
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 25000);
      try {
        const response = await fetch("/api/email/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: abort.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Email status could not be confirmed.");
        if (data.status === "accepted") {
          status.textContent = "Microsoft 365 accepted your email for sending. This does not confirm that OTS has received or read it.";
          sendEmail.textContent = "Submitted to Microsoft 365"; available = false;
        } else if (data.status === "failed") {
          status.textContent = "Microsoft 365 did not accept this email. Check the sending account setup before trying a new attempt.";
          payload = null; body.readOnly = false; reply.readOnly = false; confirm.disabled = false; confirm.checked = false;
          sendEmail.textContent = "Send a new attempt";
        } else if (data.status === "unknown") {
          status.textContent = "Sending is in progress or the result is uncertain. Check the sending mailbox before making another attempt. Checking status will not send a duplicate.";
          sendEmail.textContent = "Check this attempt's status";
        } else throw new Error("Unexpected email status. Check this attempt before trying again.");
      } catch {
        status.textContent = "Could not confirm the email status. Keep this page open and check this attempt again; the same request will not be sent twice.";
        sendEmail.textContent = "Check this attempt's status";
      } finally {
        clearTimeout(timer); mailSending = false; controls(); sendEmail.disabled = !available;
      }
    });
    form.append(label, body, replyLabel, reply, confirmLabel, sendEmail);
    card.append(heading, note, to, subject, form, status);
    $("messages").append(card);
    scroll();
    try {
      const response = await fetch("/api/email/status");
      const config = await response.json();
      if (version !== epoch) return;
      available = response.ok && config.available === true && config.recipient === email.to;
      status.textContent = available ? "Microsoft 365 sending is configured. Review the message before sending." : "Microsoft 365 sending is not configured yet. You can prepare your email, but sending needs the team's approved account setup.";
      sendEmail.disabled = !available;
    } catch { status.textContent = "Cannot check the email configuration. Try preparing the email again when the server is available."; }
  }
  function validChat(data) {
    return typeof data.reply === "string" && Array.isArray(data.sources) && data.sources.every(s => typeof s === "string") &&
      typeof data.offer_options === "boolean" && typeof data.escalate === "boolean" && (data.escalate ? ["fixed_topic", "low_confidence", "user_request"].includes(data.escalation_reason) : data.escalation_reason === null);
  }
  function validEscalation(data) {
    return (data.email === null && typeof data.clarifying_question === "string" && data.clarifying_question.length > 0) ||
      (data.clarifying_question === null && data.email && ["to", "subject", "body"].every(key => typeof data.email[key] === "string"));
  }
  async function execute() {
    if (!pending || busy) return;
    const version = epoch;
    busy = true;
    $("error").hidden = true; $("retry").hidden = true; controls();
    controller = new AbortController();
    const timer = setTimeout(() => controller?.abort(), 15000);
    try {
      const path = pending;
      const request = path === "/api/chat" ? { messages: history, mode } : { messages: history };
      const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: controller.signal });
      const data = await response.json();
      if (version !== epoch) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Hawk could not respond. Please try again.");
      if (path === "/api/chat") {
        if (!validChat(data)) throw new Error("Hawk returned an unexpected reply. Please try again.");
        history.push({ role: "bot", text: data.reply });
        message("bot", data.reply, data.sources);
        pending = null;
        $("options").hidden = !data.offer_options;
        if (mode === "diagnose") completed = true;
        save();
      } else {
        if (!validEscalation(data)) throw new Error("Hawk returned an unexpected draft. Please try again.");
        if (data.clarifying_question) {
          history.push({ role: "bot", text: data.clarifying_question });
          message("bot", data.clarifying_question);
          save();
        } else {
          completed = true;
          save();
          emailCard(data.email);
        }
        pending = null;
      }
    } catch (error) {
      if (version !== epoch) return;
      $("error").textContent = error.name === "AbortError" ? "Hawk took too long to respond. Try again or start a new chat." : (error instanceof TypeError ? "Cannot reach Hawk. Check that the local server is running, then try again." : error.message);
      $("error").hidden = false; $("retry").hidden = false;
    } finally {
      clearTimeout(timer);
      if (version === epoch) {
        busy = false; controller = null; controls();
        if (pending && $("error").hidden) execute();
        else if (!pending) $("message").focus();
      }
    }
  }
  function send(text) {
    text = text.trim();
    if (!text || busy || pending || mailSending) return;
    // Leave room for the reply and an automatic escalation question.
    if (history.length >= 56 || history.reduce((n, m) => n + m.text.length, text.length) > 21000) {
      $("error").textContent = "This conversation is full. Finish reviewing any email, then start a new chat.";
      $("error").hidden = false; return;
    }
    history.push({ role: "user", text });
    message("user", text);
    save();
    $("message").value = ""; $("chips").hidden = true;
    pending = escalating ? "/api/escalate" : "/api/chat";
    execute();
  }
  function reset() {
    if (mailSending) return;
    epoch++; controller?.abort(); controller = null;
    history = []; escalating = false; mode = "conversation"; pending = null; busy = false; completed = false;
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* Nothing to clear if storage is unavailable. */ }
    $("messages").replaceChildren(); $("message").value = "";
    $("error").hidden = true; $("retry").hidden = true; $("chips").hidden = false; $("options").hidden = true;
    message("bot", greeting); controls(); $("message").focus();
  }
  function open(value) {
    $("chat").hidden = !value; $("launcher").hidden = value;
    $("launcher").setAttribute("aria-expanded", String(value));
    (value ? $("message") : $("launcher")).focus();
  }
  $("launcher").addEventListener("click", () => open(true));
  $("close").addEventListener("click", () => open(false));
  $("reset").addEventListener("click", reset);
  $("retry").addEventListener("click", execute);
  $("composer").addEventListener("submit", event => { event.preventDefault(); send($("message").value); });
  $("choose-email").addEventListener("click", () => { if (busy || pending || mailSending) return; escalating = true; pending = "/api/escalate"; execute(); });
  $("choose-diagnose").addEventListener("click", () => { if (busy || pending || mailSending) return; escalating = false; mode = "diagnose"; pending = "/api/chat"; execute(); });
  document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => send(button.dataset.question)));
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !$("chat").hidden) open(false); });
  if (!restore()) reset();
})();
