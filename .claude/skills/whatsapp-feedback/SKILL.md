---
name: whatsapp-feedback
description: Pull feedback from a WhatsApp Web chat or group on demand via browser automation, deduped against a local CSV cursor of what was already seen. Use when the user asks to check WhatsApp (or a named chat/group) for feedback on this repo.
---

Read-only, on-demand check of a WhatsApp chat/group for feedback on this repo,
using the existing logged-in WhatsApp Web session in Chrome. Never live/polling
— this runs once per invocation and stops.

Args: `<chat name>` (required unless resuming a single already-tracked chat —
see step 1), optional `since=YYYY-MM-DD` to override the tracked cursor for
this one run without changing what gets saved as "checked so far."

## 1. Resolve the target chat and the "since" cursor

- Read `.claude/state/whatsapp-feedback-log.csv` (header:
  `chat_name,last_seen_at,last_checked_at`; create it with just that header if
  the file is missing).
- If no chat name was given: if the CSV tracks exactly one chat, ask to
  confirm using that one; if it tracks several, list them and ask which one
  (or for a new name) — don't guess.
- Match the given name against `chat_name` case-insensitively.
  - `since=` passed → use that date as this run's cursor, regardless of the
    CSV row.
  - Else, existing row → use its `last_seen_at` as the cursor.
  - Else, first time seeing this chat → ask the user how far back to start
    rather than picking a default lookback window; there's no safe guess for
    an unfamiliar chat's volume.

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
  than one chat matches the given name, don't guess — list the matches (chat
  name plus whether it's a group or a DM) and ask the user which one they
  meant before reading anything.
- **Strictly read-only.** Never click send, never type into the message
  composer, never touch delete/clear-chat/archive/exit-group controls, and
  don't click anything that could trigger a confirmation dialog (per the
  standing rule against triggering browser dialogs). Only scroll, search, and
  read.
- WhatsApp Web loads history lazily on scroll. Scroll up, extracting text as
  you go (`get_page_text` / `read_page`), until you reach messages dated on or
  before the cursor date. Stop there — don't read further back than the
  cursor requires.
- If scrolling stalls or a tool call fails repeatedly (2-3 attempts), stop,
  report what was actually read and how far back it reached, and ask how to
  proceed rather than looping.

## 4. Extract and summarize feedback

- From messages newer than the cursor, pull out what reads as feedback on
  this repo/project — bugs, feature requests, complaints, praise, open
  questions. Skip pure logistics/chatter.
- For each item, give sender, date, and the message (quoted or tightly
  paraphrased) so the user can trace it back to the source.
- Group related messages into one item rather than listing every line
  separately.

## 5. Update the cursor

- Advance `last_seen_at` only to the date of the newest message actually
  read this run. If step 3 stopped early, don't advance past what was
  covered.
- Upsert the chat's row in `.claude/state/whatsapp-feedback-log.csv`
  (`last_checked_at` = now, ISO timestamp, audit-only — not used for dedup).
  Chat names can contain commas, quotes, or emoji — write the row with a real
  CSV writer/library (or at minimum wrap `chat_name` in double quotes and
  double up any embedded quotes) rather than a raw comma-joined string, so a
  name like "Thandkoi Clinics, Feedback" can't split into an extra column.
- Tell the user the new cursor so they know where the next run will resume.

## Notes

- `.claude/state/` is gitignored — this is a personal local tracking file,
  not repo documentation, and may reference chat/contact names.
- This skill only ever reads forward from a saved cursor; it never
  re-summarizes messages already covered by a prior run for the same chat.
