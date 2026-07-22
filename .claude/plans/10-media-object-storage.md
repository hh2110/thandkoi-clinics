# Plan 10 — Media object storage (Cloudflare R2)

**One-line:** serve and persist user-uploaded media (Wagtail images/documents)
from an S3-compatible object store, because WhiteNoise serves static only and
Render's disk is ephemeral.

## Background — why now

The first image uploaded to production (2026-07-22, via Wagtail admin) rendered
as a broken thumbnail. Root cause, confirmed against prod:

- `/media/…` returns **404** while `/static/…` returns **200**. The route that
  serves `MEDIA_URL` (`config/urls.py`) is gated behind `if settings.DEBUG:`, so
  in prod (`DEBUG=False`) nothing serves media. WhiteNoise deliberately serves
  `STATIC_URL` only.
- Even if it were served, `STORAGES["default"]` was `FileSystemStorage` writing
  to `MEDIA_ROOT = BASE_DIR/"media"`, and `render.yaml` mounts **no persistent
  disk** — Render's container filesystem is ephemeral, so uploads vanish on the
  next deploy/restart.

This gap has existed since the prod launch; it surfaced the first time media was
uploaded. It is not caused by the `v2026.07.22` release.

## Goal & scope

**Goal:** uploaded media works in production — served from a durable, public,
CDN-fronted URL that survives deploys.

**In scope**
- Add `django-storages[s3]` (pulls `boto3`).
- Point `STORAGES["default"]` at an S3-compatible bucket in `prod.py`, configured
  from env (Cloudflare R2).
- Declare the `MEDIA_*` env vars in `render.yaml` (secrets, `sync: false`).
- Document the new secrets (`docs/deploying.md`) and the one-off bucket setup
  (below).

**Out of scope**
- **Dev/local** keeps `FileSystemStorage` + the DEBUG-gated `/media/` route —
  unchanged. This mirrors the existing static split (dev uses finders, prod uses
  the manifest backend).
- Migrating any already-uploaded prod media (there is one broken test image;
  re-upload after the bucket is live).
- A custom media subdomain is optional — the R2 public bucket URL works as
  `MEDIA_CUSTOM_DOMAIN` until a domain is wired up.

## Decisions

- **Object storage, not a Render persistent disk.** A Render disk pins the
  service to a single instance and still needs a media-serving view; object
  storage is the standard Wagtail-on-Render answer — durable, horizontally
  scalable, CDN-frontable, no app route.
- **Cloudflare R2** as the S3-compatible provider: zero egress fees, cheapest at
  this scale, S3 API works unchanged via `boto3`/`django-storages`. Any S3
  provider (AWS S3, Backblaze B2) would drop in by swapping the endpoint + keys.
- **Required in prod, fail loud.** The five `MEDIA_*` vars are read
  unconditionally in `prod.py` (matching prod's existing "fail fast if a secret
  is missing" doctrine). Consequence: the bucket + secrets must be set **before**
  the next deploy, or the service won't boot. This is deliberate — it prevents
  silently regressing to broken/ephemeral media.
- **Public, unsigned URLs** (`querystring_auth = False`): clinic media is public
  content; plain cacheable URLs are simpler and CDN-friendly. `default_acl =
  None` because R2 rejects ACLs; `file_overwrite = False` so same-named uploads
  don't clobber.

### Privacy note
This bucket holds **published website media only** (Wagtail images/documents an
editor uploads). It is **not** the PHI pipeline — that data is aggregated in
memory and discarded per CLAUDE.md invariant #1 and never touches this store.

Because the bucket is public and served with unsigned URLs
(`querystring_auth = False`), **Wagtail's private/restricted collections are not
enforceable here** — any object is world-readable by URL. That is acceptable
under the "clinic media is public content" assumption above; do not upload
anything access-restricted to this store expecting the collection gate to hold.

## Precedent map (Stage 7)

- **`STORAGES["default"]` override in `prod.py`** — mirrors the existing
  `STORAGES["staticfiles"]` override in `dev.py`, and prod's own pattern of
  importing `STORAGES` from base and reassigning one key.
- **Env-driven config, `sync: false` secrets** — mirrors `DATABASE_URL` /
  `ANTHROPIC_API_KEY` in `prod.py` + `render.yaml`.
- **django-storages S3 backend + R2 options** — grounded against the
  django-storages S3 docs and Cloudflare R2's S3-compatibility guide (no in-repo
  precedent; greenfield). `region_name="auto"`, `signature_version="s3v4"`,
  `default_acl=None` are R2's documented requirements.

## Feature flag (Stage 6)

No runtime flag. Per the repo convention (no plan uses one pre-launch), the
natural gate is environment separation: prod uses R2, dev/CI use the filesystem.
The change is prod-only settings + a dependency; there is no partial user-facing
slice to guard.

## Release plan (Stage 10)

- **How it ships:** one PR (this plan). Then the maintainer does the one-off
  bucket setup, sets the five Render secrets, and deploys a **new tag** via the
  Deploy workflow (`docs/deploying.md`). Order matters: **secrets first, deploy
  second** (the service fails to boot otherwise).
- **Gating check:** after deploy, upload an image in Wagtail admin and confirm
  the thumbnail renders; `curl -I` an object URL under `MEDIA_CUSTOM_DOMAIN`
  returns `200`.
- **Rollback:** redeploy the previous tag (`gh workflow run deploy.yml -f
  ref=v2026.07.22`). Note that reverting the *code* re-breaks media, so rollback
  here is for the app, not the storage decision.
- **Who's informed:** maintainer only (solo project).

### First-time setup (maintainer, one-off)
1. **Cloudflare R2** — create a bucket (e.g. `thandkoi-media`). Enable public
   access (R2 public bucket URL, or attach a custom domain like
   `media.thandkoiclinics.com`).
2. **R2 API token** — create an S3 access key/secret scoped to the bucket.
3. **Render** (service → Environment) — set:
   - `MEDIA_BUCKET_NAME` = the bucket name
   - `MEDIA_S3_ENDPOINT_URL` = `https://<accountid>.r2.cloudflarestorage.com`
   - `MEDIA_S3_ACCESS_KEY_ID` / `MEDIA_S3_SECRET_ACCESS_KEY` = the token pair
   - `MEDIA_CUSTOM_DOMAIN` = the public host serving objects — **bare hostname
     only, no `https://` and no trailing slash** (e.g. `media.thandkoiclinics.com`
     or the `pub-xxxx.r2.dev` public URL). django-storages adds the scheme; a
     value with `https://` breaks every media URL.
4. Deploy a fresh tag and run the gating check.

## Tasks

- [x] Add `django-storages[s3]` to `pyproject.toml`; refresh `uv.lock`.
- [x] Configure `STORAGES["default"]` (R2) in `config/settings/prod.py`.
- [x] Declare `MEDIA_*` vars in `render.yaml` (`sync: false`).
- [x] Update `docs/deploying.md` Secrets section.
- [ ] Maintainer: create bucket + set secrets (first-time setup above).
- [ ] Deploy a new tag; run the gating check; re-upload the test image.

## Acceptance criteria

- With the five `MEDIA_*` vars set, prod boots and an image uploaded in Wagtail
  admin renders on the public site.
- An object URL under `MEDIA_CUSTOM_DOMAIN` returns `200` and survives a redeploy.
- Dev/CI are unchanged: tests run on `FileSystemStorage`, no bucket required.
