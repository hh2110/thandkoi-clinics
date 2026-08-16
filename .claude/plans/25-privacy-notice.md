# Plan 25 — A privacy notice for the public site

**One line:** publish a privacy notice at `/en/privacy/`, linked from the
site-wide footer, in which **every claim is verified against this repository's
own code** — and guard it with tests so it cannot silently go stale.

## Background

`thandkoiclinics.com` has been live since 2026-07 and has no privacy notice.
Verified 2026-08-16: `https://thandkoiclinics.com/privacy` returns **302 to
`/en/privacy/`** (`LocaleMiddleware` redirecting an unrouted path — the same
302 Plan 23 D9 documents) and `/en/privacy/` returns **404**.

That is a real gap rather than a formality. The site:

- loads a third-party analytics script on every page (Umami Cloud, Plan 12
  Track B) — confirmed live: `data-website-id="53a9…"` is present in the
  production HTML source;
- sends error and performance events to Sentry — confirmed live via the
  Sentry MCP: 57,965 spans in the trailing 24h, org `thandkoi-clinics`,
  project `python-django`, region `de.sentry.io` (Sentry's **EU** region);
- embeds a **Google Maps iframe** on the Contact page (`ContactBankSettings.
  map_embed_url`, rendered by `core/contact_page.html`) — the one third party
  on this site that can set its own cookies in a visitor's browser;
- publishes pages derived from patient data through the Plan 08 pipeline.

An equivalent notice was written and merged for the sibling project `ks1`
([PR #38](https://github.com/hh2110/ks1/pull/38)) and is the precedent for
tone, structure and the guard tests. It is **not** the precedent for content:
that app has accounts, cookies and no analytics; this one has none of the
first two and does have analytics.

## Decisions

**D1 — The controller/processor split is stated, and is the one thing the
maintainer must confirm before this merges.** For KS1 the operator and the
controller are the same company. Here they are not, and the code shows a split
rather than a single answer:

| Data | Who decides why it is processed | Role |
|---|---|---|
| Clinic export / de-identified visit rows | The clinic — its software produces the export, its staff choose to upload it, its trustees decide what gets published | **Clinic = controller**, North West Data Products = **processor** (it built and runs the pipeline on the clinic's behalf), Anthropic = sub-processor |
| Enquiries and donation contacts | The clinic — they arrive at the clinic's own email/phone/bank, which this site only *displays* | **Clinic = controller.** The website is not in the path at all |
| Site analytics (Umami) and diagnostics (Sentry) | North West Data Products — it chose the tools, holds both accounts, and used their output for its **own** operational decisions (Plans 23 and 24 sized the Neon compute problem from Umami's human-traffic figure and Sentry's span counts) | **North West Data Products = controller in its own right** for this narrow set |

The third row is the part that does not follow the KS1 answer. Determining the
purpose of a processing operation yourself is what makes you a controller for
it, and Plans 23/24 are the evidence that this telemetry is collected for the
operator's purposes, not merely on the clinic's instruction.

**Confidence: the shape is well-grounded in the code; the legal entities and
the applicable jurisdiction are not this repo's to decide.** The notice names
The Thandkoi Clinics and North West Data Products Ltd on that basis, and the
template carries a prominent comment saying so. The maintainer must confirm
before this leaves draft.

**D2 — English only, deliberately, and the page says so.** The page lives
inside `i18n_patterns` like every other public page, so it serves at
`/en/privacy/` *and* `/ur/privacy/`. Its prose is **not** wrapped in
`{% translate %}`, unlike the site chrome. Reason: `locale/` contains nothing
but `.gitkeep` — this repo has never had a translation catalogue, so
`{% translate %}` would mark strings no one can translate today, and an
unreviewed Urdu rendering of a document whose entire value is accuracy is
worse than one honest language. The page carries a visible line inviting a
reader to ask for it in Urdu or Pashto.

*Reversal condition:* when a real translation workflow lands (a `.po`
catalogue, or `wagtail-localize` for content), translate this page then, with
a person reviewing the result — not before.

**D3 — A hardcoded template and a plain Django view, not a Wagtail page.**
This is the decision that most obviously cuts against the repo's precedent for
content pages (About/Contact/Donate are all `Page` subclasses whose prose an
editor maintains in `/admin/`), so it is recorded rather than assumed.

The notice's whole value is that every sentence is checked against code. Three
consequences follow, and all three point the same way:

1. As Wagtail content it would live in PostgreSQL, so **`git log` would not be
   its history** and a review would never see a change to it.
2. The guard tests below can only assert against a file in the repo. A test
   cannot meaningfully guard a paragraph an editor can rewrite in the admin
   between deploys.
3. The rule "when the code changes, the notice changes in the same PR" is only
   enforceable if the notice *is* code.

The in-repo precedent this follows is Plan 18's `robots.txt` view — a plain
non-Wagtail view whose content is a repo constant precisely because it must
not drift. It differs from that precedent in exactly one respect: it sits
**inside** `i18n_patterns`, because unlike `robots.txt`/`healthz` it is a page
a human reads, not infrastructure (`config/urls.py`'s own docstring draws that
line).

**D4 — Say what the free-text columns actually are.** The README's summary line
reads "raw patient data (PHI) is never stored and never sent to any AI model."
Checked against `apps/pipeline/models.py`, that is true of *direct identifiers*
and misleading about the rest: `DeidentifiedVisit` holds **seven raw free-text
clinical columns** (Plan 11 Track B8/B9), and they are sent to Anthropic. The
notice states this plainly, along with the two controls that make it defensible
(the clinic software structurally cannot accept an identifier into those
fields; the N=3 floor, `MIN_GROUP_VISITS_TO_SUMMARISE`, gates what publishes).
A notice that repeated the README's headline would be the kind of
plausible-sounding-but-wrong document this project's culture exists to prevent.

**D5 — Read the contact address from `ContactBankSettings`, don't hardcode it.**
Same reasoning as the footer, the Contact page and the Donate page: the address
lives in the running application (architecture brief), so a correction is one
admin edit. Degrades to a link to the Contact page when unset, mirroring
`footer.html`'s "coming soon" fallback.

## Every claim, and where it was checked

| Claim in the notice | Verified against |
|---|---|
| Nothing you type is collected — no contact form, no sign-up, no payment | Only `forms.Form` in the tree is `pipeline/forms.py` (staff upload, permission-gated). `apps/core/middleware.py`'s docstring records the same check on 2026-08-16; re-verified live |
| No cookies for a visitor | `curl -D -` against `https://thandkoiclinics.com/en/` returns **no `Set-Cookie`**. `SESSION_COOKIE_HTTPONLY`/`CSRF_COOKIE_*` in `prod.py` apply to signed-in staff only |
| Theme choice stays in the browser | `localStorage` key `thandkoi-theme`, `templates/base.html` + `static/js/theme-toggle.js` |
| Umami: cookieless, aggregate-only; what we can see | `templates/base.html` script tag + `UMAMI_WEBSITE_ID`; the metric list is CLAUDE.md's description of the actual saved board |
| Sentry carries no IP address and no cookies | `send_default_pii` is never set anywhere in the repo; with it off, `sentry_sdk` `_wsgi_common.SENSITIVE_ENV_KEYS` strips `REMOTE_ADDR`, `X-Forwarded-For`, `X-Real-IP` and `Cookie` (read in `.venv`, sentry-sdk 2.66.1) |
| Sentry carries no request body | `max_request_body_size="never"` + `observability.before_send` / `before_send_transaction` |
| Sentry stores in the EU | `find_organizations` reports `regionUrl: https://de.sentry.io` |
| The browser's User-Agent *is* recorded | `observability._tag_user_agent` (Plan 24 D7) |
| No server-side access log | `render.yaml` `startCommand` has no `--access-logfile`; `observability.py:62` states the same consequence |
| Fonts self-hosted, no CDN | `test_no_third_party_font_or_cdn_requests` |
| Photos load from `media.thandkoiclinics.com` | `prod.py` `STORAGES["default"]` (Cloudflare R2, `MEDIA_CUSTOM_DOMAIN`); confirmed in live page source |
| The Contact page embeds a Google map | `core/contact_page.html` iframe; live source shows `www.google.com/maps/embed?pb=…` |
| Raw export never reaches disk or the database | `pipeline/middleware.MemoryOnlyUploadHandlerMiddleware` + `admin_views` docstring — no `TemporaryFileUploadHandler` in the chain |
| Name / father's name / address / MR # / vitals never read | `parser_tkc_daily_v1` — no column lookup exists for them beyond the sniff signature |
| Date of birth read only to derive an age band, then discarded | `_as_dob` is a local; `DeidentifiedVisit` has no DOB field |
| What is kept per visit | `DeidentifiedVisit`'s field list, in full |
| Seven free-text columns are kept and are sent to a model | `DeidentifiedVisit` 2026-07-23 block; `apps/pipeline/freetext.py` module docstring |
| Group summaries need 3+ patients | `freetext.MIN_GROUP_VISITS_TO_SUMMARISE = 3`, enforced in `report_publishing` |
| Report pages are `noindex` | `pipeline/daily_report_page.html` `{% block meta_robots %}` |
| No figure ever comes from the model | CLAUDE.md invariant #3; `DailyAggregate.as_dict` is the whole payload |

## Scope

In scope:
- `apps/core/views.py` — a `privacy` view (plain `render`, no database work).
- `config/urls.py` — `privacy/` inside `i18n_patterns`, above the Wagtail
  catch-all.
- `apps/core/templates/core/privacy.html` — the notice.
- `templates/partials/footer.html` — the link, in `site-footer__meta`.
- `apps/core/tests.py` — five guards (below).
- One line in the architecture brief's website-structure list.

Out of scope (deliberately):
- Any deploy. Deploys here are manual, tag-based and the maintainer's
  (`docs/deploying.md`); this PR ships code only.
- Translating the notice — D2.
- A cookie banner. There is nothing to consent to: no cookie is set for a
  visitor and the analytics are cookieless. The Google Maps iframe is the one
  arguable case and is disclosed in text instead.
- Changing anything about what the pipeline collects. This plan describes the
  system; it does not alter it.

## The guards

A hand-written notice drifts silently, so five tests, adapted from the KS1 set:

1. **It is public** — `/en/privacy/` returns 200 signed out, and the assertion
   is on a phrase unique to the page (not the word "Privacy", which the footer
   now puts on every page).
2. **It is reachable in both languages** — `/ur/privacy/` also serves, so the
   page is genuinely inside `i18n_patterns` rather than accidentally pinned to
   English.
3. **The link is in the shared footer partial** — asserted against
   `footer.html` itself, so moving it into a single page's template fails,
   then confirmed to actually render on a real page.
4. **`DeidentifiedVisit`'s fields must exactly match what the notice
   describes** — equality, not a subset, so a field being *removed* is caught
   too. This is the repo's counterpart to KS1's `Child` guard: it is the model
   that holds everything the notice claims to describe about patients.
5. **The notice's third-party list must match what is actually wired** — in
   *both* directions. A tracker installed while the notice does not name it
   fails; the notice naming one that is no longer installed fails too. KS1's
   version only guarded the first direction, which is all it needed with no
   trackers wired; here three third parties are live, so over-claiming is the
   likelier drift.

## Precedent map

| Element | Mirrors |
|---|---|
| The view | `apps.core.views.robots_txt` — a plain non-Wagtail view in the same module, content-as-code precisely so it can't drift |
| URL registration | `config/urls.py`'s own docstring rule — content is language-prefixed, infrastructure is not; so this goes **inside** `i18n_patterns`, unlike `robots.txt` |
| Template location | `apps/core/templates/core/` — where every other core template lives |
| Page shape | `core/about_page.html` — `<section class="section">` + `<div class="wrapper prose">`, no new CSS |
| Contact address | `templates/partials/footer.html` / `core/contact_page.html` — read `settings.core.ContactBankSettings`, never a hardcoded value |
| Footer link | `site-footer__meta`, the existing flex row that already holds the copyright and tagline; `.site-footer a` is already themed for both modes |
| Guard tests | `ks1` PR #38's four; plus the two-way third-party guard, which is new |
| Test style | `apps/core/tests.py`'s `test_robots_txt_*` block — a docstring saying which decision the test locks and what failure it prevents |

## Feature flag

None, consistent with every plan in this repo. A flag would be wrong here on
its own terms: a privacy notice that is only sometimes visible is not a notice.
There is also nothing to roll back to — the current state is a 404.

## Release plan

1. Merge, then deploy via the normal manual tag-based flow
   (`scripts/release.sh`) — **not** as part of this PR.
2. Check `https://thandkoiclinics.com/en/privacy/` serves 200 and that
   `https://thandkoiclinics.com/privacy` now follows its 302 to a real page.
3. Check the footer link renders on the home page in both themes.
4. Confirm the Contact & Bank Details setting's email is populated, or the
   page falls back to the Contact link (it does either way — but the email is
   the better outcome).

**Gating check:** the maintainer's confirmation of D1 (who the controller is)
before the PR leaves draft. Nothing else on this page is a judgement call.
**Rollback:** re-deploy the previous tag; the page simply 404s again.
**Informed:** the clinic's trustees should know the notice names them as
controller for the clinic data before it is public.
