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

**Opt-in gate for the multi-agent Workflow pass (added 2026-07-23 — it burns
too many tokens to run by default).** Do NOT call the `Workflow` tool as the
default review mechanism. The default for every mandatory pre-PR review —
first pass or a re-run — is the single-pass manual read (step 1 below). Only
use the `Workflow`-tool-backed multi-agent pass (step 3) when I have
explicitly asked for it earlier in the current session (e.g. "run the full
workflow review," "do a deeper/ultra-style pass"). If a change looks risky
enough that you think the heavier pass is warranted, **ask me first** —
never invoke it unprompted, regardless of branch size or risk.

1. **Default: single-pass manual read.** Read the scoped diff yourself
   (uncommitted changes + commits on this branch not on `main`, or just the
   file(s) named by the caller for a re-run) and review it carefully in one
   pass — the same care as any other review, just without spawning
   subagents.
2. Report the verified findings with the `ReportFindings` tool
   (`{level: "medium", findings}` — "medium" reflects a single careful pass
   without independent subagent verification, distinct from the workflow's
   "high" floor in step 3), most-severe first, an empty array if nothing
   survived review. Do not also print the findings as prose. Note in your
   response that this was a single-pass manual review, not the multi-agent
   workflow.
3. **Only if I've explicitly asked for the multi-agent workflow pass in this
   session:** call the `Workflow` tool with
   `{name: "code-review", args: "<level> [target]"}` — level is always
   `high` (its floor — there is no `low`/`medium`; never `xhigh`/`max`
   unless I explicitly ask for a deeper pass than that); target is the
   file/path/instruction scoping this pass (omit only for a first,
   whole-branch pass; every re-run after fixing findings should pass a
   `target` naming just the file(s) the fix touched, per the token-cost
   rationale above — don't re-scan the whole branch diff again unless the
   fix was broad enough that a targeted pass could miss a knock-on effect
   elsewhere). The workflow runs in the background; wait for its completion
   notification instead of polling. Report via `ReportFindings` the same as
   step 2, noting this was the multi-agent workflow pass.
4. If the built-in workflow is unavailable when step 3 applies (unknown-name
   error or the Workflow tool is absent), fall back to the single-pass
   manual review described in step 1 and say so explicitly.

Scope note: this wrapper reviews the local diff only. It is not a substitute
for `/code-review ultra`, which stays user-triggered.
