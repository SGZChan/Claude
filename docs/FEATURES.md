# Laya features

Open **Features** in the dashboard to switch things on and off, or apply a preset (Minimal, Personal assistant, Developer, Researcher, Private/offline, Everything, Defaults). A turned-off feature disappears from the model's tool list and refuses to run. Turning a feature on also turns on what it needs; turning one off also turns off what depends on it. Choices persist across restarts.

Tools marked 🔒 always ask for your approval before running. Tools marked 🌐 use the network and are hard-blocked by **Offline mode**.

| Category | Feature | Default | What it does |
|---|---|---|---|
| Assistant | Notes & memory | on | `notes_add`, `notes_list`, `memory_search` |
| | To-do list | on | `todo_add`, `todo_list`, `todo_done` |
| | Reminders | on | `reminder_add`, `reminder_list` + background job that fires due reminders |
| | Daily brief | on | `daily_brief`: todos, reminders, notes, activity |
| | Auto morning brief | off | job: stores the brief once a day |
| | Private journal | on | `journal_add`, `journal_search` |
| | Calendar (.ics) | off | `calendar_upcoming` from .ics files in the workspace (no recurrence expansion) |
| Files & knowledge | File & document helper | on | list/read/**write 🔒**/search/summarise/extract/stats |
| | Knowledge base (RAG) | on | `kb_ingest`, `kb_ask` (with sources), `kb_sources` |
| | Auto-index workspace | off | job: re-index changed files every minute |
| Data | Calculator & converters | on | arithmetic, units, date maths, time |
| | Data wrangling | on | CSV head/stats/filter/group, JSON query |
| Web | Web digest | off | fetch **🔒🌐** + summarise allow-listed pages |
| | Offline mode | off | blocks every network tool |
| Developer | Developer helper | on | code search, read-only git, allow-listed tests **🔒** |
| | Code sandbox | off | Python snippets and read-only shell **🔒** (high risk) |
| Communication | Message triage | on | classify, prioritise, draft replies, triage a folder of .eml files |
| Utilities | Utilities | on | password / passphrase generator, text stats |
| | Backup & export | on | download database + workspace as a .zip |
| Learning | System One skills | on | learned skills run with no model call |
| | Reflection | on | one-line lesson after each run |
| | Memory recall | on | lessons/corrections/notes fed into the prompt |
| | Self-practice | off | job: practise verifiable tasks every 30 min |
| Automation | Scheduler | on | recurring goals (Schedules page) |
| | Plugins | off | load your own Python tools from `<data>/plugins` (high risk: plugin code is unsandboxed) |

Many tools enabled at once would overflow a 0.5B model's context, so only the ~10 tools most relevant to the current goal are shown to the model.

## Roadmap: more features worth adding
- **Real embeddings** (fastembed / bge-small) to replace hashed embeddings; better knowledge-base recall.
- **PDF / DOCX / OCR ingestion** for the knowledge base.
- **Email connector** (IMAP read-only) feeding Message triage; **CalDAV** for calendars with recurrence.
- **MCP adapter** so Laya can use (and expose) MCP tools.
- **Local web search** via a self-hosted SearXNG instance.
- **Voice**: local speech-to-text (whisper.cpp) and text-to-speech.
- **Notifications**: desktop / push alerts when a reminder fires.
- **Skill sharing**: export/import skills and feature presets as files; skill editor with dry-run.
- **Fine-tune assistant**: one-click LoRA training from the exported JSONL, with before/after eval.
- **Expense & habit trackers** built on the CSV tools.
- **Multi-user + auth**, PWA install, and a mobile-friendly quick-capture page.
- **Eval suite** dashboard: regression-test skills and prompts after each change.
