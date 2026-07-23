#!/usr/bin/env bash
# Cut a release tag and deploy it to production.
#
# Codifies docs/deploying.md: verify preconditions, cut a date-based tag off
# origin/main, trigger the Deploy workflow (workflow_dispatch, tag-only),
# watch it, then health-check production. See that doc for the full runbook
# and rationale (no staging environment, tag-addressed deploys, why
# workflow_dispatch is the approval gate).
#
# Usage:
#   scripts/release.sh                    # cut a new date-based tag from origin/main, deploy it
#   scripts/release.sh --ref vYYYY.MM.DD  # deploy an existing tag as-is (rollback/redeploy) — no new tag cut
#   scripts/release.sh --yes              # skip the interactive y/N confirmation (see below)
#
# Requires: gh (authenticated), git, jq, curl.
#
# By default the script prompts for an explicit y/N confirmation before
# tagging or deploying. --yes skips that prompt and proceeds straight to
# tagging/deploying once every precondition above it (main == origin/main,
# CI green on that commit, deploy-hook secret present) has already passed —
# it does not skip or weaken any of those checks, only the final "do you
# want to do this" prompt.
#
# 2026-07-23 policy reversal (maintainer decision, explicit and informed):
# this flag did not exist until today. It was deliberately absent through
# five rounds of code review specifically to stop an AI agent from deploying
# to production on its own initiative — the maintainer then asked for it
# back, was shown that tradeoff directly (this flag lets any agent session
# deploy without a human typing anything, ever), and confirmed they wanted
# it anyway. --yes still requires being explicitly passed on every
# invocation; nothing here changes the default (still fully interactive) or
# weakens any precondition check above.

set -euo pipefail

REPO="hh2110/thandkoi-clinics"
HEALTH_URL="https://thandkoiclinics.com/healthz"

log()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
# Prompts $1, returns success only on a "y"/"Y" answer. Gates on `read`'s own
# exit status, not just its output — a closed/non-interactive stdin makes
# `read` fail outright, which would otherwise let `set -e` kill the script
# before the caller's own abort message ever prints.
confirm() {
  local reply=""
  read -r -p "$1 " reply || true
  [[ "$reply" =~ ^[Yy]$ ]]
}

REF=""
YES=0
REMOTE_MAIN=""  # only set on the "cut a new tag" path; kept defined (empty)
                # here so the --ref path's later fallback echo can't trip
                # `set -u`'s unbound-variable check

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 2 ]] || fail "--ref requires a tag argument, e.g. --ref v2026.07.20"
      REF="$2"
      shift 2
      ;;
    --yes)
      YES=1
      shift
      ;;
    -h|--help)
      # Only the header comment block (shebang through the blank line before
      # `set -euo pipefail`) — not every inline "# --- Section ---" comment
      # in the script body, which `grep '^#' "$0"` used to leak into --help.
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

command -v gh   >/dev/null || fail "gh CLI not found."
command -v jq   >/dev/null || fail "jq not found."
command -v curl >/dev/null || fail "curl not found."
gh auth status >/dev/null 2>&1 || fail "gh is not authenticated (run: gh auth login)."

# --- Preconditions -----------------------------------------------------------

log "Fetching origin"
git fetch origin --tags

if [[ -z "$REF" ]]; then
  log "Checking main is up to date with origin/main"
  LOCAL_MAIN=$(git rev-parse main 2>/dev/null || echo "")
  REMOTE_MAIN=$(git rev-parse origin/main)
  if [[ "$LOCAL_MAIN" != "$REMOTE_MAIN" ]]; then
    fail "Local main ($LOCAL_MAIN) != origin/main ($REMOTE_MAIN). Run: git checkout main && git pull --ff-only"
  fi
  echo "OK — main == origin/main ($REMOTE_MAIN)"

  log "Checking CI is green on that commit"
  CI_RUN=$(gh run list --repo "$REPO" --branch main --workflow CI --limit 20 --json headSha,conclusion,status \
    | jq -c --arg sha "$REMOTE_MAIN" '[.[] | select(.headSha == $sha)] | first')
  if [[ "$CI_RUN" == "null" || -z "$CI_RUN" ]]; then
    fail "No CI run found yet for $REMOTE_MAIN. Wait for CI to run on this commit before releasing."
  fi
  STATUS=$(echo "$CI_RUN" | jq -r '.status')
  CONCLUSION=$(echo "$CI_RUN" | jq -r '.conclusion')
  [[ "$STATUS" == "completed" ]] || fail "CI for $REMOTE_MAIN is still running (status: $STATUS). Wait for it to finish."
  if [[ "$CONCLUSION" != "success" ]]; then
    fail "CI for $REMOTE_MAIN did not pass (conclusion: $CONCLUSION). Do not release a red commit."
  fi
  echo "OK — CI passed on $REMOTE_MAIN"
else
  log "Deploying an existing tag ($REF) — skipping main/CI checks"
  git rev-parse "refs/tags/$REF" >/dev/null 2>&1 || fail "Tag '$REF' not found locally after fetch. Check the tag name."
fi

log "Checking the deploy hook secret exists"
SECRETS_ERR="$(mktemp)"
trap 'rm -f "$SECRETS_ERR"' EXIT  # fail() exits before an inline `rm -f` would run, so this must be a trap, not a step
SECRET_NAMES="$(gh api "repos/$REPO/environments/production/secrets" --jq '.secrets[].name' 2>"$SECRETS_ERR")" || {
  fail "Could not check the production environment's secrets (gh api call failed): $(cat "$SECRETS_ERR"). This is a permissions/network/auth problem, not necessarily a missing secret — check \`gh auth status\` before assuming First-time setup is incomplete."
}
if ! grep -qx "RENDER_DEPLOY_HOOK_URL" <<<"$SECRET_NAMES"; then
  fail "RENDER_DEPLOY_HOOK_URL is not set on the production environment. See docs/deploying.md's 'First-time setup' — this is a one-off, maintainer-only step."
fi
echo "OK — RENDER_DEPLOY_HOOK_URL is configured"

# --- Determine / cut the tag -------------------------------------------------

if [[ -z "$REF" ]]; then
  PREV_TAG=$(git tag --list --sort=-creatordate | head -1 || true)
  log "What's shipping since the last release"
  if [[ -n "$PREV_TAG" ]]; then
    echo "Previous release: $PREV_TAG"
    echo
    git log --oneline "$PREV_TAG"..origin/main
  else
    echo "No previous release tag found — this looks like the first release."
    git log --oneline origin/main | head -20 || true  # head closes the pipe early once satisfied; without this, SIGPIPE + pipefail kills the whole script under set -e
  fi

  BASE_TAG="v$(date +%Y.%m.%d)"
  REF="$BASE_TAG"
  SUFFIX=2
  while git rev-parse "refs/tags/$REF" >/dev/null 2>&1; do
    REF="${BASE_TAG}-${SUFFIX}"
    SUFFIX=$((SUFFIX + 1))
  done
  echo
  echo "New release tag: $REF (at $REMOTE_MAIN)"
fi

# --- Confirm ------------------------------------------------------------------

log "Ready to deploy"
echo "Tag:    $REF"
echo "Commit: $(git rev-parse "$REF" 2>/dev/null || echo "$REMOTE_MAIN")"
echo "Target: production (https://thandkoiclinics.com)"
echo

if [[ "$YES" == "1" ]]; then
  echo "--yes passed — skipping the interactive confirmation."
else
  confirm "Deploy $REF to production? [y/N]" \
    || { echo "Aborted — nothing was tagged or deployed."; exit 1; }
fi

# --- Cut and push the tag (only when we made a new one) ---------------------

if ! git rev-parse "refs/tags/$REF" >/dev/null 2>&1; then
  log "Tagging $REF"
  # Tag the exact SHA already verified as CI-green and shown to the operator
  # ($REMOTE_MAIN), not the mutable `origin/main` ref name — a concurrent
  # fetch (another terminal, an IDE, a second invocation) between that
  # verification and this line could otherwise move origin/main out from
  # under an interactive confirm prompt, tagging a commit that was never
  # actually checked. This branch only runs on the "cut a new tag" path,
  # where $REMOTE_MAIN is always set.
  git tag "$REF" "$REMOTE_MAIN"
  git push origin "$REF"
fi

# --- Trigger the deploy -------------------------------------------------------

log "Triggering the Deploy workflow for $REF"
# 2-minute buffer before "now", not "now" itself — GitHub's server-recorded
# createdAt could otherwise sort earlier than a client clock running a few
# seconds fast, silently dropping the real run out of the candidate list.
# Widening the window is safe: candidates are still positively confirmed by
# their own log content below, not by timing alone. date -r (BSD/macOS)
# falls back to date -d @ (GNU/Linux).
SINCE_EPOCH=$(($(date -u +%s) - 120))
TRIGGERED_AT=$(date -u -r "$SINCE_EPOCH" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d "@$SINCE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)
gh workflow run deploy.yml --repo "$REPO" -f ref="$REF"

# Find the run this dispatch actually created — never assume it's whatever
# `--limit 1` returns, which can be stale (deploy.yml's concurrency group is
# cancel-in-progress: false, so an older still-running/queued deploy run can
# rank above the new one) or simply not registered yet. `gh run list --json`
# has no field for a workflow_dispatch input's value, so createdAt alone
# can't tell two candidate runs apart when more than one was dispatched in
# the same window — positively confirm the match by grepping each
# candidate's own log for deploy.yml's "Deploying tag $REF (...)" line
# (from its "Verify the ref is a release tag" step) rather than trusting
# timing alone.
#
# Poll for up to 5 minutes (60 x 5s), not 2 — the same cancel-in-progress:
# false concurrency group means a freshly-dispatched run can sit queued
# behind a prior still-running deploy for a while before its log has
# anything to match against. A candidate is only ever ruled out (added to
# CHECKED and never re-examined) once its own run has reached a terminal
# `status` of "completed" AND its log still doesn't match — checking status
# first (cheap, no --log fetch) before trusting a miss is required because a
# run's own life cycle can be shorter than one 5s poll tick (observed
# 2026-07-23: a real deploy run completed in 15s total, and its "Deploying
# tag $REF (" line — logged partway through, once the "Verify the ref" step
# runs — didn't exist yet the moment this loop first saw the run as a
# candidate; grepping that in-progress run's partial log came back with no
# match, and the old code treated that miss as final, permanently ruling out
# the one run that was actually deploying and later failing the whole
# script even though the deploy itself succeeded). Runs still queued/
# in_progress are cheap to re-poll every tick via --json status alone; only
# a completed run's log is ever grepped, and only a completed run with no
# match is ever added to CHECKED.
RUN_ID=""
CHECKED=" "
for _ in $(seq 1 60); do
  CANDIDATES=$(gh run list --repo "$REPO" --workflow deploy.yml --limit 10 \
    --json databaseId,createdAt,event \
    | jq -r --arg since "$TRIGGERED_AT" \
      '[.[] | select(.event == "workflow_dispatch" and .createdAt >= $since)]
       | sort_by(.createdAt) | .[].databaseId')
  for candidate in $CANDIDATES; do
    [[ "$CHECKED" == *" $candidate "* ]] && continue
    CANDIDATE_STATUS=$(gh run view "$candidate" --repo "$REPO" --json status --jq .status 2>/dev/null || echo "")
    [[ "$CANDIDATE_STATUS" == "completed" ]] || continue
    CANDIDATE_LOG=$(gh run view "$candidate" --repo "$REPO" --log 2>/dev/null || echo "")
    # An empty fetch (transient API error, or logs not archived yet even
    # though status just flipped to completed) is left off CHECKED so it
    # gets retried next tick — only a non-empty log that genuinely lacks the
    # match line is treated as a confirmed miss.
    [[ -z "$CANDIDATE_LOG" ]] && continue
    if grep -qF "Deploying tag ${REF} (" <<<"$CANDIDATE_LOG"; then
      RUN_ID="$candidate"
      break
    fi
    CHECKED="${CHECKED}${candidate} "
  done
  [[ -n "$RUN_ID" ]] && break
  sleep 5
done
[[ -n "$RUN_ID" ]] || fail "Could not find the workflow_dispatch run for $REF (none created at/after $TRIGGERED_AT confirmed deploying it after 5 minutes). The tag was already pushed — this may just mean the run is still queued behind another in-progress deploy (deploy-production's concurrency group doesn't cancel a prior run), not that anything failed. Check the Actions tab before assuming otherwise: https://github.com/$REPO/actions/workflows/deploy.yml"

echo "Watching run $RUN_ID"
gh run watch "$RUN_ID" --repo "$REPO" --exit-status

log "Deploy workflow finished — Render is now building/swapping"
echo "Track build/migrate progress in the Render dashboard."
echo "This script only confirms the trigger fired; it does not wait for Render's build."

# --- Health check --------------------------------------------------------------

log "Health-checking production (a few retries — Render's swap isn't instant)"
for i in 1 2 3 4 5 6; do
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$HEALTH_URL" || echo "000")
  if [[ "$CODE" == "200" ]]; then
    echo "OK — $HEALTH_URL returned 200"
    exit 0
  fi
  echo "Attempt $i: $HEALTH_URL returned $CODE — retrying in 15s"
  sleep 15
done

fail "$HEALTH_URL did not return 200 after several retries. Check the Render dashboard directly before assuming this deploy is healthy."
