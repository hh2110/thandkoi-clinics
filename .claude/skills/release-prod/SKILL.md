---
name: release-prod
description: >-
  Release the current main to production (Render) following the repo's
  tag-gated deploy runbook. Use when the user asks to "release to prod",
  "deploy", "ship to production", "cut a release", or "roll back production".
  Codifies docs/deploying.md: verify preconditions, cut a date-based release
  tag, run the Deploy workflow against that tag, watch it, and confirm the
  service is healthy. Never deploys without an explicit human go-ahead.
---

# Release to production

This skill ships **code** to production. It does **not** publish AI-drafted
**content** — that is Wagtail's in-app draft → preview → publish gate
(CLAUDE.md invariant #4). Source of truth for everything below is
[docs/deploying.md](../../../docs/deploying.md); if this skill and that doc ever
disagree, the doc wins and this skill should be updated.

## Non-negotiables

- **Deploying is an irreversible, outward action.** Never trigger a deploy
  without an explicit "yes, deploy" from the user in this session. Show them
  exactly what will ship (tag + short SHA + one-line summary of what's in it)
  and get confirmation first.
- **You do not provision infrastructure or handle secrets.** Creating the Neon
  DB / Render service and setting `DATABASE_URL`, `ANTHROPIC_API_KEY`, or
  `RENDER_DEPLOY_HOOK_URL` are maintainer-only, done in the Render/Neon/GitHub
  dashboards. If any is missing, stop and hand that step back to the user.
- **Deploys target a tag, never a branch or raw SHA.** The Deploy workflow
  rejects anything that is not a tag.
- **One environment: production.** There is no staging. The `workflow_dispatch`
  trigger *is* the safety gate.

## Preconditions — check all before proposing a deploy

Run these read-only checks and report the result of each. If any fails, stop and
tell the user what to fix; do not proceed to tagging.

1. **On main, up to date.**
   ```bash
   git fetch origin
   git rev-parse main origin/main   # must be equal
   ```
   The release is cut from `origin/main`. If local `main` is behind, `git pull`
   first.

2. **CI is green on the commit being released.**
   ```bash
   gh run list --branch main --workflow CI --limit 1 \
     --json headSha,conclusion,status
   ```
   The latest CI run for that SHA must be `conclusion=success`. Never release a
   red or still-running commit.

3. **The deploy hook secret exists.** The Deploy workflow hard-fails without it.
   ```bash
   gh api repos/hh2110/thandkoi-clinics/environments/production/secrets \
     --jq '.secrets[].name'
   ```
   `RENDER_DEPLOY_HOOK_URL` must be listed. (You can see the name, not the
   value.) If it is absent, the one-off setup in docs/deploying.md
   ("First-time setup") is not done — stop and hand back to the maintainer;
   the deploy cannot work yet.

4. **Sanity on what will ship.** Summarise the diff since the last deployed tag
   so the user knows what they're releasing:
   ```bash
   git tag --list --sort=-creatordate | head -1        # previous release tag
   git log --oneline <previous-tag>..origin/main        # what's new (omit range if no prior tag)
   ```

## Cut and push the release tag

Tags are **lightweight and date-based** (`vYYYY.MM.DD`), not semver. For a second
release on the same day, append `-2`, `-3`, ….

```bash
git checkout main && git pull
TAG="v$(date +%Y.%m.%d)"                     # e.g. v2026.07.21
# If TAG already exists, bump the suffix: v2026.07.21-2, -3, …
git tag "$TAG"
git push origin "$TAG"
```

Confirm the tag points at the intended commit (`git rev-parse "$TAG"` ==
`origin/main`). Optionally offer to publish a GitHub Release from the tag with
auto-generated notes — a free "what shipped and when" log.

## Trigger the deploy — only after explicit confirmation

```bash
gh workflow run deploy.yml -f ref="$TAG"
```

Then watch the run to completion and report the result:

```bash
sleep 5
gh run list --workflow deploy.yml --limit 1 --json databaseId,status,conclusion
# then, with the id from above:
gh run watch <run-id> --exit-status        # or poll gh run view <run-id>
```

The workflow verifies the ref is a real tag, then calls the Render deploy hook
for that exact commit. A `2xx` from the hook means the deploy was *triggered* —
Render then builds and swaps. Track build/migrate progress in the **Render
dashboard**; the GitHub run only confirms the trigger fired.

## Verify production is healthy

After Render reports the deploy live, confirm the app is up:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://<production-host>/healthz
```

`200` means the new version is serving. If the host/custom domain isn't known,
ask the user (or read it from the Render service). Migrations run automatically
as the `preDeployCommand` before traffic swaps — you do not run them manually.

## Rollback

Deploys are tag-addressed, so rollback is precise: re-run the workflow with the
**previous** tag.

```bash
gh workflow run deploy.yml -f ref="<previous-tag>"   # e.g. v2026.07.20
```

Confirm with the user before rolling back (it is another production change), then
watch and health-check exactly as above.

## What this skill will NOT do

- Create or modify Render/Neon services, or set any secret.
- Deploy a branch, a raw SHA, or an untagged commit.
- Deploy a commit whose CI is red or unfinished.
- Trigger a deploy or rollback without an explicit in-session go-ahead.
- Decide whether AI-drafted content is fit to publish (that's the Wagtail
  draft workflow, a separate gate).
