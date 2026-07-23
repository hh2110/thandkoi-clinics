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
#   scripts/release.sh                 # cut a new date-based tag from origin/main, deploy it
#   scripts/release.sh --ref vYYYY.MM.DD   # deploy an existing tag as-is (rollback/redeploy) — no new tag cut
#   scripts/release.sh --yes           # skip the confirmation prompt (non-interactive use)
#   scripts/release.sh --dry-run       # run every precondition check and print the plan, then stop
#   scripts/release.sh --skip-ci-check # allow releasing a commit whose CI shows "cancelled" (not "success") —
#                                       # only for a verified false negative (e.g. a concurrency-group
#                                       # cancellation during a fast-merge burst); a real failure still blocks.
#                                       # Always prompts its own explicit confirmation, even with --yes.
#
# Requires: gh (authenticated), git, jq, curl.
#
# --yes is for a human who is already sure (e.g. re-running this script
# themselves after reading its dry-run output), or a deliberately unattended
# context the maintainer set up themselves (a scheduled job, a second
# invocation in the same session right after a human already said yes to
# this exact release). An AI agent must NEVER pass --yes on its own
# initiative — get an explicit "yes, deploy" from the user in the current
# session first, same as this script's deleted predecessor (the release-prod
# skill) required. A human typing the command themselves is the "yes"; an
# agent typing it on their behalf is not, unless the human said so first.

set -euo pipefail

REPO="hh2110/thandkoi-clinics"
HEALTH_URL="https://thandkoiclinics.com/healthz"

REF=""
ASSUME_YES=0
DRY_RUN=0
SKIP_CI_CHECK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 2 ]] || { echo "--ref requires a tag argument, e.g. --ref v2026.07.20" >&2; exit 1; }
      REF="$2"
      shift 2
      ;;
    --yes|-y)
      ASSUME_YES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --skip-ci-check)
      SKIP_CI_CHECK=1
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
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

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
    if [[ "$CONCLUSION" == "cancelled" && "$SKIP_CI_CHECK" -eq 1 ]]; then
      echo "WARNING — CI for $REMOTE_MAIN shows 'cancelled', not 'success'."
      echo "This is only safe if you've separately confirmed the code is good (e.g."
      echo "its PR passed CI before merge, and this push-triggered run was cancelled"
      echo "by a concurrency group during a fast-merge burst — a known false"
      echo "negative, not a real CI failure). If CI was cancelled for a real reason,"
      echo "answering yes below ships an unverified commit to production."
      # --skip-ci-check always prompts its own confirmation, even under --yes —
      # stacking two unattended bypasses (skip the CI gate AND skip confirming
      # it) is exactly the scenario this exists to prevent (found by
      # code-review-tc).
      read -r -p "Proceed anyway, treating this as a verified false negative? [y/N] " CI_CONFIRM
      [[ "$CI_CONFIRM" =~ ^[Yy]$ ]] || fail "Aborted — CI did not pass and the cancellation was not confirmed as a false negative."
    else
      fail "CI for $REMOTE_MAIN did not pass (conclusion: $CONCLUSION). Do not release a red commit. If you've verified this is a false negative (e.g. a concurrency-group cancellation during a fast-merge burst, not a real failure), re-run with --skip-ci-check."
    fi
  else
    echo "OK — CI passed on $REMOTE_MAIN"
  fi
else
  log "Deploying an existing tag ($REF) — skipping main/CI checks"
  git rev-parse "refs/tags/$REF" >/dev/null 2>&1 || fail "Tag '$REF' not found locally after fetch. Check the tag name."
fi

log "Checking the deploy hook secret exists"
if ! gh api "repos/$REPO/environments/production/secrets" --jq '.secrets[].name' 2>/dev/null | grep -qx "RENDER_DEPLOY_HOOK_URL"; then
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
    git log --oneline origin/main | head -20
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

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry run — stopping before any tag/deploy action"
  echo "Would tag: $REF"
  echo "Would deploy: $REF"
  exit 0
fi

# --- Confirm ------------------------------------------------------------------

log "Ready to deploy"
echo "Tag:    $REF"
echo "Commit: $(git rev-parse "$REF" 2>/dev/null || echo "$REMOTE_MAIN")"
echo "Target: production (https://thandkoiclinics.com)"
echo

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Deploy $REF to production? [y/N] " CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted — nothing was tagged or deployed."; exit 1; }
fi

# --- Cut and push the tag (only when we made a new one) ---------------------

if ! git rev-parse "refs/tags/$REF" >/dev/null 2>&1; then
  log "Tagging $REF"
  git tag "$REF" origin/main
  git push origin "$REF"
fi

# --- Trigger the deploy -------------------------------------------------------

log "Triggering the Deploy workflow for $REF"
TRIGGERED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh workflow run deploy.yml --repo "$REPO" -f ref="$REF"

# Find the run this dispatch actually created — never assume it's whatever
# `--limit 1` returns, which can be stale (deploy.yml's concurrency group is
# cancel-in-progress: false, so a still-running prior deploy run can rank
# above the new one) or simply not registered yet. Poll for a
# workflow_dispatch run created at/after TRIGGERED_AT instead.
RUN_ID=""
for _ in $(seq 1 12); do
  RUN_ID=$(gh run list --repo "$REPO" --workflow deploy.yml --limit 10 \
    --json databaseId,createdAt,event \
    --jq --arg since "$TRIGGERED_AT" \
      '[.[] | select(.event == "workflow_dispatch" and .createdAt >= $since)]
       | sort_by(.createdAt) | first | .databaseId // empty')
  [[ -n "$RUN_ID" ]] && break
  sleep 5
done
[[ -n "$RUN_ID" ]] || fail "Could not find the workflow_dispatch run this triggered (none created at/after $TRIGGERED_AT after 60s). Check the Actions tab directly: https://github.com/$REPO/actions/workflows/deploy.yml"

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
