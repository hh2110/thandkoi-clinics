---
name: cleanup-worktrees
description: Sweep .claude/worktrees/ and local branches for finished (merged) work and remove it safely. Use when the user asks to "clean up worktrees", "clean up branches", or after confirming a PR merged and wanting the local leftovers gone.
---

Reclaim disk space and branch clutter left behind by `EnterWorktree` sessions
and manual `git worktree add` usage, **without ever discarding work that
isn't safely elsewhere.** Deletion is the whole point of this skill, so
default to caution per the global safety rules — investigate before
deleting, prefer confirmation over guessing, and never silently drop
uncommitted or unpushed content.

## 1. Build the inventory

Run these to see the full picture before touching anything:

```
git fetch origin --prune -q
git worktree list --porcelain
ls -la .claude/worktrees/
git branch -vv
gh pr list --state merged --limit 30 --json number,title,headRefName,mergedAt
```

`.claude/worktrees/` can contain three kinds of entries:

- **Registered worktrees** (appear in `git worktree list`) — a live worktree
  with a `.git` file pointing at `.git/worktrees/<name>`.
- **Orphaned directories** — left on disk after a worktree was removed but
  cleanup didn't finish (e.g. a locked/large `.venv` blocked deletion, or a
  prior session skipped `ExitWorktree`). No entry in `git worktree list`; the
  `.git` file may be missing entirely or may point at a `.git/worktrees/<name>`
  dir that no longer exists (dangling).
- The main worktree itself (skip it — never remove).

Run `git worktree prune -v` first; it clears git's bookkeeping for anything
already gone from disk, and its output tells you what it dropped.

## 2. Classify each candidate (worktree or local branch)

For every registered worktree and every local branch, determine:

1. **Is its branch merged into `main`?**
   `git merge-base --is-ancestor <sha> main` (or `git branch --merged main`
   for local branches). A branch pointing at a commit that's an ancestor of
   `main` is done — its work already landed.
2. **Does the branch have an open, non-merged PR?** Cross-check with
   `gh pr list` / `gh pr view <branch> --json state`. If a PR is open or in
   draft, it's active — never touch it.
3. **Does the worktree have uncommitted changes or untracked files?**
   `git -C <path> status --short`. Anything here is unsaved and would be
   permanently lost on deletion.
4. **Does the worktree/branch have commits not on any remote?**
   `git -C <path> log @{u}.. --oneline` (or compare against `origin/main` if
   no upstream) — unpushed commits are also unsaved from the repo's
   perspective.
5. **Is it the worktree the current session is sitting in, or one that shows
   changes you didn't make?** Never touch a worktree whose current state you
   can't explain — another concurrent session may be actively using it.

## 3. Decide, per the same rule every time

- **Merged branch, no open PR, clean status, nothing unpushed** → safe.
  Remove the worktree (`git worktree remove <path>`, or `--force` only if
  `status --short` was empty — never force through real diffs), delete the
  local branch (`git branch -d`, not `-D`), and ask before deleting the
  *remote* branch (deleting a remote ref is shared-state and hard to
  reverse — confirm even if the user pre-approved the local half, unless
  they've explicitly pre-authorized it for this run).
- **Orphaned directory with no `.git` file, or a dangling one** → inspect
  before deleting even though git itself can't identify it:
  - If everything inside is build/dependency artifacts (`.venv`,
    `__pycache__`, `node_modules`, `.ruff_cache`, and the like) with no
    source-level diff against current `main`, it's safe to `rm -rf`.
  - Otherwise, diff its tracked-looking source files against the same paths
    on `main` (`diff -rq <dir>/apps apps`, etc.). If everything there matches
    (or is strictly behind, i.e. older/superseded) current `main`, it's safe.
    If it contains content that exists nowhere else in the repo's history,
    treat it like unpushed work below.
- **Anything uncommitted, unpushed, or unmerged** → never auto-delete. Surface
  exactly what's at risk (the diff, the untracked files, the branch's commits
  ahead of any merge base) and let the user choose: extract it (patch file,
  new branch, or copy the files out) then delete, or delete outright, or leave
  it. Use `AskUserQuestion` when there's more than one reasonable path and the
  choice isn't yours to make.
- **Anything with an open PR or that looks like it might be actively in use**
  (e.g. HEAD moved to it very recently, or its worktree shows changes that
  don't match anything you did this session) → stop and flag it. Concurrent
  sessions can be working the same repo; never touch a worktree whose state
  you can't explain.

## 4. Report

Summarize what was removed (worktrees + local + remote branches) and what was
left behind and why, so the user has a clean record of the sweep.
