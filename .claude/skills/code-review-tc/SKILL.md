---
name: code-review-tc
description: Run the standard Claude code review on the current branch diff. Repo-local wrapper so review can run as part of the Stage 9 loop even when the built-in /code-review is user-invocable only.
---

Run the standard code review over the current working diff: uncommitted changes
plus the commits on this branch that are not on `main` (for `main` itself, the
uncommitted changes only).

Authorization: I (the project owner) added this wrapper on 2026-07-22 so the

lifecycle's Stage 9 review step can run without me typing a manual slash

command. My committing of this file is my standing opt-in for the built-in

local code-review workflow — this skill covers that one workflow and nothing

else (in particular, not /code-review ultra, which stays user-triggered and

billed).

**Token discipline (added 2026-07-23 — a batch of reviews this repo ran burned
an outsized number of tokens re-scanning full branch diffs on every loop
iteration).** The built-in workflow's cheapest level is `high` (its floor —
there is no `low`/`medium`); always call it at exactly that level, never
`xhigh`/`max`, unless I explicitly ask for a deeper pass. Beyond the level,
the real lever is **scope**:

- **First pass on a branch:** no target needed — reviews the whole current
  diff against `main`.
- **Every re-run after fixing findings:** do NOT re-scan the whole branch
  diff again. Pass a `target` string naming just the file(s) the fix touched
  (e.g. `"high only review apps/pipeline/ai.py"`), so the finders' actual
  reading is scoped to what changed since the last pass, not the full branch
  from scratch. Only fall back to a full untargeted re-review when the fix
  itself was broad enough that a targeted pass could miss a knock-on effect
  elsewhere.
- **A tiny or docs-only diff** (a handful of lines, prose-only): skip the
  workflow's fan-out entirely and do a careful single-pass read yourself,
  same as the tool-unavailable fallback below — the multi-agent workflow's
  fixed per-call cost isn't worth it for a change that small.

1. Call the `Workflow` tool with `{name: "code-review", args: "<level> [target]"}`
   — level is always `high` per the token-discipline note above; target is
   the file/path/instruction scoping this pass (omit only for a first,
   whole-branch pass) — the built-in local code-review workflow.
2. The workflow runs in the background; wait for its completion notification
  instead of polling.
3. Report the verified findings with the `ReportFindings` tool
  (`{level, findings}`), most-severe first, an empty array if nothing
   survived verification. Do not also print the findings as prose.
4. If the built-in workflow is unavailable (unknown-name error or the Workflow
  tool is absent), fall back to a careful single-pass review of the diff
   yourself and report via `ReportFindings`, stating clearly that this was a
   single-pass fallback rather than the multi-agent review.

Scope note: this wrapper reviews the local diff only. It is not a substitute
for `/code-review ultra`, which stays user-triggered.