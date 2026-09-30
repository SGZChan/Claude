"""Email / text triage. Works on pasted text or .eml files in the workspace; no mail account needed."""
from __future__ import annotations

import email
import re
from email import policy

from .helpers import Ctx
from .registry import ToolError

LEXICON = {
    "urgent": ["urgent", "asap", "immediately", "deadline", "by eod", "right away", "time-sensitive", "today"],
    "meeting": ["meeting", "call", "schedule", "calendar", "invite", "zoom", "reschedule", "available", "sync"],
    "invoice": ["invoice", "payment", "receipt", "overdue", "bill", "amount due", "refund"],
    "newsletter": ["unsubscribe", "newsletter", "weekly digest", "view in browser", "no-reply", "noreply"],
    "spam": ["winner", "free money", "click here", "lottery", "prize", "limited offer", "act now", "congratulations you"],
}
PRIORITY = {"urgent": 3, "invoice": 2, "meeting": 2, "other": 2, "personal": 1, "newsletter": 1, "spam": 0}
REPLIES = {
    "urgent": "Thanks for flagging this. I'm looking into it now and will get back to you shortly.",
    "meeting": "Thanks for reaching out. I'd be happy to meet. Could you share a couple of time options that work for you?",
    "invoice": "Thanks for sending this over. I'll review it and confirm once payment is processed.",
    "newsletter": "",
    "spam": "",
    "other": "Thanks for your message. I've noted it and will follow up soon.",
    "personal": "Thanks for the note! I'll reply properly as soon as I can.",
}
TONES = {"polite": ("Hello,\n\n", "\n\nKind regards"), "casual": ("Hi,\n\n", "\n\nCheers"), "formal": ("Dear Sir or Madam,\n\n", "\n\nSincerely")}


def triage(text: str) -> dict:
    low = text.lower()
    scores = {c: sum(low.count(w) for w in ws) for c, ws in LEXICON.items()}
    top, hits = max(scores.items(), key=lambda kv: kv[1])
    category = top if hits else ("personal" if re.search(r"\b(thanks|hi|hey|dear)\b", low) else "other")
    if scores["spam"] >= 2:
        category = "spam"
    priority = PRIORITY[category]
    if "?" in text and category not in ("spam", "newsletter"):
        priority = max(priority, 2)
    actions = []
    if "?" in text:
        actions.append("answer question")
    for m in re.findall(r"(?:by|before|on)\s+(\d{4}-\d{2}-\d{2}|monday|tuesday|wednesday|thursday|friday|tomorrow|eod)", low):
        actions.append(f"deadline: {m}")
    return {"category": category, "priority": priority, "actions": list(dict.fromkeys(actions))}


def fmt_triage(t: dict) -> str:
    return f"category={t['category']} priority={t['priority']}/3 actions=" + ("; ".join(t["actions"]) or "none")


def install(ctx: Ctx) -> None:
    reg = ctx.reg

    @reg.register("triage_text", "classify a message: category, priority and required actions (email triage, inbox)", {"text": "message text"}, feature="text_triage")
    def triage_text(text: str) -> str:
        return fmt_triage(triage(str(text)))

    @reg.register("draft_reply", "draft a reply to a message for you to approve", {"text": "message to reply to", "tone": "polite | casual | formal"}, feature="text_triage", optional=("tone",))
    def draft_reply(text: str, tone: str = "polite") -> str:
        cat = triage(str(text))["category"]
        body = REPLIES[cat]
        if not body:
            return f"No reply needed (category: {cat})."
        head, tail = TONES.get(str(tone), TONES["polite"])
        return head + body + tail

    @reg.register("triage_inbox", "triage every .eml email file in a workspace folder, most important first", {"path": "folder with .eml files"}, feature="text_triage")
    def triage_inbox(path: str) -> str:
        files = ctx.text_files(str(path), {".eml"})
        if not files:
            raise ToolError("no .eml files found")
        rows = []
        for p in files[:100]:
            msg = email.message_from_string(p.read_text(errors="replace"), policy=policy.default)
            body = msg.get_body(preferencelist=("plain",))
            text = f"{msg['subject'] or ''}\n{body.get_content() if body else ''}"
            t = triage(text)
            rows.append((t["priority"], f"[{t['category']}/{t['priority']}] {msg['from'] or '?'}: {msg['subject'] or '(no subject)'}"))
        return "\n".join(r for _, r in sorted(rows, key=lambda x: -x[0])[:15])
