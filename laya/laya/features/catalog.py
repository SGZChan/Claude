"""Every switchable feature Laya ships with. Tools declare their feature id via @reg.register(feature=...)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    id: str
    name: str
    description: str
    category: str
    default: bool = True
    requires: tuple[str, ...] = ()
    risk: str = "low"  # low | medium | high - how much it can touch outside Laya
    example: str = ""  # a goal the user can try
    job: str = ""  # background job id, if any
    interval: int = 0  # seconds between job runs
    kind: str = "tools"  # tools | policy | behaviour | job


CATALOG: list[Feature] = [
    # ---- Assistant
    Feature("notes", "Notes & memory", "Save notes and search everything Laya remembers.", "Assistant", example="Remember that the wifi password is on the fridge"),
    Feature("todos", "To-do list", "Add, list and complete tasks.", "Assistant", example="Add todo buy milk"),
    Feature("reminders", "Reminders", "Set reminders in plain time ('in 30 minutes', 'tomorrow 9:00'). A background job fires them.", "Assistant", job="reminders", interval=15, example="Remind me to stretch in 30 minutes", kind="tools"),
    Feature("daily_brief", "Daily brief", "One-paragraph summary of today: todos, reminders, notes and Laya's activity.", "Assistant", example="Give me my daily brief"),
    Feature("auto_brief", "Auto morning brief", "Generates the brief automatically once a day and stores it in memory.", "Assistant", default=False, requires=("daily_brief",), job="auto_brief", interval=3600, kind="job"),
    Feature("journal", "Private journal", "Write journal entries with a mood and search them later.", "Assistant", example="Journal: had a great day hiking"),
    Feature("calendar", "Calendar (.ics)", "Read upcoming events from .ics files you drop in the workspace. Read-only; recurring events are not expanded.", "Assistant", default=False, example="What are my upcoming events?"),
    # ---- Files & knowledge
    Feature("file_helper", "File & document helper", "List, read, search, summarise and extract data from workspace files. Writing files needs your approval.", "Files & knowledge", risk="medium", example="Summarize notes.txt"),
    Feature("knowledge_base", "Knowledge base (RAG)", "Index your documents and answer questions from them with sources.", "Files & knowledge", example="Ask my knowledge base about the project deadline"),
    Feature("watch_folder", "Auto-index workspace", "Background job that re-indexes new or changed workspace files every minute.", "Files & knowledge", default=False, requires=("knowledge_base",), job="watch_folder", interval=60, kind="job"),
    # ---- Data
    Feature("calculator", "Calculator & converters", "Arithmetic, unit conversion, date maths, current time.", "Data", example="Convert 5 miles to km"),
    Feature("data_wrangling", "Data wrangling", "Inspect, filter, group and compute statistics on CSV files; query JSON.", "Data", example="csv stats sales.csv amount"),
    # ---- Web
    Feature("web_digest", "Web digest", "Fetch allow-listed pages and summarise them into memory. Every fetch needs your approval.", "Web", default=False, risk="medium", example="Digest https://en.wikipedia.org/wiki/Llama"),
    Feature("offline_mode", "Offline mode", "Hard-blocks every tool that uses the network. Great for private / edge use.", "Web", default=False, kind="policy"),
    # ---- Developer
    Feature("dev_helper", "Developer helper", "Search code, read-only git status/log/diff, and run allow-listed test commands (approval required).", "Developer", risk="medium", example="git status"),
    Feature("code_sandbox", "Code sandbox", "Run short Python snippets and read-only shell commands. Always needs approval.", "Developer", default=False, risk="high", example="Run python: print(2**10)"),
    # ---- Communication
    Feature("text_triage", "Message triage", "Classify emails/messages (urgent, meeting, invoice, spam...), find actions, draft replies, triage a folder of .eml files.", "Communication", example="Triage: URGENT please send the invoice by Friday"),
    # ---- Utilities
    Feature("utilities", "Utilities", "Password and passphrase generator, text statistics.", "Utilities", example="Generate a passphrase"),
    Feature("backup", "Backup & export", "Download a full snapshot (database + workspace) from the dashboard.", "Utilities", kind="policy"),
    # ---- Learning
    Feature("system_one", "System One skills", "Fast path: run learned skills with no model call. Off = always reason with the model.", "Learning", kind="behaviour"),
    Feature("reflection", "Reflection", "After each run Laya writes a one-line lesson and stores it.", "Learning", kind="behaviour"),
    Feature("memory_recall", "Memory recall", "Feed relevant lessons, corrections and notes into the model's prompt.", "Learning", kind="behaviour"),
    Feature("self_practice", "Self-practice", "Background job: practise verifiable tasks every 30 minutes so skills get learned while idle.", "Learning", default=False, job="self_practice", interval=1800, kind="job"),
    # ---- Automation & platform
    Feature("scheduler", "Scheduler", "Run recurring goals on a timer (Schedules page).", "Automation", kind="job"),
    Feature("plugins", "Plugins", "Load your own Python tools from the plugins folder. Plugins run with full privileges, so only enable this for code you trust.", "Automation", default=False, risk="high", kind="tools"),
]

BY_ID = {f.id: f for f in CATALOG}

PRESETS: dict[str, dict] = {
    "minimal": {"label": "Minimal", "description": "Notes, calculator and learning only.",
                "features": ["notes", "calculator", "system_one", "memory_recall", "reflection"]},
    "assistant": {"label": "Personal assistant", "description": "Tasks, reminders, journal, briefs, triage.",
                  "features": ["notes", "todos", "reminders", "daily_brief", "auto_brief", "journal", "calendar", "text_triage", "utilities", "calculator", "scheduler", "backup", "system_one", "memory_recall", "reflection"]},
    "developer": {"label": "Developer", "description": "Code search, git, tests, data and docs.",
                  "features": ["notes", "file_helper", "knowledge_base", "watch_folder", "dev_helper", "code_sandbox", "data_wrangling", "calculator", "utilities", "scheduler", "backup", "system_one", "memory_recall", "reflection"]},
    "researcher": {"label": "Researcher", "description": "Documents, web digests, data and a journal.",
                   "features": ["notes", "journal", "file_helper", "knowledge_base", "web_digest", "data_wrangling", "calculator", "utilities", "backup", "system_one", "memory_recall", "reflection"]},
    "private": {"label": "Private / offline", "description": "Everything that works without a network; offline mode on.",
                "features": [f.id for f in CATALOG if f.id not in ("web_digest", "plugins", "code_sandbox")] + ["offline_mode"]},
    "everything": {"label": "Everything", "description": "Turn on every feature.", "features": [f.id for f in CATALOG]},
    "default": {"label": "Defaults", "description": "Laya's recommended starting set.", "features": [f.id for f in CATALOG if f.default]},
}
