---
name: whatsapp-task-tracker
description: Track tasks the maintainer assigns to people in a WhatsApp group, detect when they're done, and draft/send follow-up reminders — on demand via browser automation. Use when the user asks to check on tasks they've assigned in WhatsApp, chase people up, or review who owes what.
---

Read/write, on-demand check of a WhatsApp chat/group for tasks the maintainer
has assigned to named people, tracked in a local CSV. Never live/polling —
this runs once per invocation and stops. Sibling to
[whatsapp-feedback](../whatsapp-feedback/SKILL.md); mirrors its cursor/dedup
pattern but adds task tracking and, as its one deliberate exception, sends
messages.

Default chat: **Thandkoi Clinic Core Group**. Args: optional `<chat name>` to
target a different chat, optional `since=YYYY-MM-DD` to override the tracked
cursor for this one run without changing what gets saved as "checked so far."

## Decision: why detection is confirmed, not silent, and sending needs a yes every run

(2026-07-25) The maintainer's first ask was full automation — auto-parse
assignments, auto-detect completions, auto-post reminders, no manual step.
Built differently, deliberately:

- **Chat text is genuinely ambiguous.** A live read of this group's history
  showed multi-day threads where even the maintainer and the doctor went back
  and forth clarifying what a message meant and who it was for. A "done" reply
  or an imperative sentence can't be reliably auto-matched to the right task
  without a human glancing at it — silent auto-tracking would confidently
  mislabel things.
- **Sending a message into the group is a standing permission-gated action**,
  not a per-project preference — every run must show the drafted text and get
  an explicit yes before anything is typed into the composer or sent. This
  applies per run; a yes on one run's reminders does not carry forward to the
  next.
- **This cannot run as an unattended background job.** WhatsApp Web needs the
  maintainer's own authenticated Chrome session; a cron/scheduled cloud agent
  has no access to it. If a recurring cadence is wanted, run this skill by
  hand or via `/loop` while the laptop and Chrome are active — it is not a
  substitute for a real always-on reminder service.

The result: capture and completion-detection surface *candidates* that the
user confirms before they change the CSV; reminders are drafted and shown as
a batch, sent only after explicit approval, one at a time.

## 1. Resolve the target chat and the cursor

- Read `.claude/state/whatsapp-tasks-log.csv` (header:
  `chat_name,last_seen_at,last_checked_at`; create it with just that header
  if missing).
- Read `.claude/state/whatsapp-tasks.csv` (header: `id,assignee,task,
  source_quote,assigned_by,assigned_date,due_date,status,completed_date,
  last_reminded_date`; create it with just that header if missing). `status`
  is one of `open`, `done`, `dismissed`.
- Chat name: use the arg if given, else default to "Thandkoi Clinic Core
  Group".
- Cursor: `since=` arg overrides for this run only; else use the chat's
  `last_seen_at` from the log; else (first run for this chat) ask the user
  how far back to start rather than guessing a lookback window.

## 2. Load the browser tools

Load every tool this needs in one call:
`ToolSearch("select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__tabs_create_mcp")`.

Call `tabs_context_mcp` first. Reuse an existing `web.whatsapp.com` tab if one
is already open; otherwise create a new tab and navigate to
`https://web.whatsapp.com`.

If the page shows a QR code instead of the chat list, stop and tell the user
to scan it in that Chrome profile — this skill cannot authenticate on their
behalf.

## 3. Open the chat and read back to the cursor

- Use WhatsApp Web's search box to find the chat by name and open it. If more
  than one chat matches, list the matches (name, group or DM) and ask which
  one rather than guessing.
- Until step 6, stay strictly read-only in the chat itself: never click send,
  never type into the composer, never touch delete/clear-chat/archive/exit
  controls, and don't click anything that could trigger a confirmation
  dialog. Only scroll, search, and read.
- WhatsApp Web loads history lazily on scroll. Scroll up, extracting text as
  you go (`get_page_text` / `read_page`), until reaching messages dated on or
  before the cursor. Stop there.
- If scrolling stalls or a tool call fails repeatedly (2-3 attempts), stop,
  report what was actually read and how far back it reached, and ask how to
  proceed rather than looping.

## 4. Extract candidate task assignments and confirm

- From messages newer than the cursor, find candidates: a core-group member
  (the maintainer or another admin) directing a specific named/tagged person
  to do something — an imperative, an @-mention plus a request, or a direct
  question that expects an action back.
- Skip pure logistics/chatter and anything already tracked (match against
  existing `source_quote`/assignee/date in the CSV to avoid duplicates).
- Present each candidate to the user: assignee, task (paraphrased), the
  source quote, and date. The user confirms, edits, or discards each one —
  don't write anything to the CSV without that.
- For each confirmed task, append a row: new `id` (increment from the
  highest existing), `assignee`, `task`, `source_quote`, `assigned_by`,
  `assigned_date`, `due_date` (blank if none was stated), `status=open`,
  `completed_date` blank, `last_reminded_date` blank.

## 5. Extract candidate completions and confirm

- For each `open` task, scan messages newer than the cursor (and newer than
  that task's `assigned_date`) from that task's `assignee` for something that
  reads as a completion signal — "done", "✅", "uploaded", a description of
  having finished the thing — in context of that task's thread.
- Present each candidate mapped to its specific task id (task text + the
  reply that looks like completion) and let the user confirm or reject before
  changing anything.
- For each confirmed completion: set `status=done`, `completed_date` = the
  message's date.

## 6. Draft and send reminders (the one exception to read-only)

- For each still-`open` task with no activity in at least N days (ask the
  user for N if not already known this session; don't default it silently),
  draft a short reminder: tag the assignee, restate the task in one line,
  ask for a status update.
- Show the **full batch** of drafts to the user before touching the composer.
  Let them edit or drop any before sending.
- Only after an explicit yes for this run: for each approved draft, click
  into the composer, type the exact approved text, send, then update that
  row's `last_reminded_date` to today. Send one at a time and confirm each
  send succeeded (message appears in the thread) before moving to the next.
- If a send fails or the composer behaves unexpectedly, stop immediately,
  report which reminders did and didn't go out, and ask before retrying —
  never re-send blind.

## 7. Update the cursor

- Advance `last_seen_at` only to the date of the newest message actually
  read this run. If step 3 stopped early, don't advance past what was
  covered.
- Upsert the chat's row in `.claude/state/whatsapp-tasks-log.csv`
  (`last_checked_at` = now, ISO timestamp, audit-only). Write CSV rows with a
  real CSV writer/library (or at minimum quote `chat_name` and double up
  embedded quotes) since names can contain commas or emoji.
- Tell the user: how many tasks are now open, how many were closed this run,
  how many reminders went out, and the new cursor.

## Notes

- `.claude/state/` is gitignored — these are personal local tracking files
  referencing real names and task content, not repo documentation.
- This skill only ever reads forward from a saved cursor; it never
  re-extracts candidates from messages already covered by a prior run for
  the same chat.
- Never invent a due date, assignee, or task text not present in the actual
  message — if a candidate is ambiguous, surface it as ambiguous and let the
  user resolve it rather than guessing.
