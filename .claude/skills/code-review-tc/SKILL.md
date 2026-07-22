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

1. Call the `Workflow` tool with `{name: "code-review"}` — the built-in
   local code-review workflow.
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