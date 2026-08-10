# Content operations

How website *content* (Wagtail pages, documents) gets created or changed,
separately from how *code* gets deployed (see [deploying.md](deploying.md)).
There are two legitimate paths — which one to use is the maintainer's call
per request, not a fixed rule.

## Two paths

| Path | Who drives it | Where | When to use |
|---|---|---|---|
| **Wagtail admin** | maintainer, by hand | browser, logged into the admin | maintainer wants hands-on control, or wants to see the editing UI before publishing |
| **Agent-driven, via SSH** | Claude Code | production shell, over SSH | maintainer asks Claude to make the change directly, especially for structured/repeatable content |

Both write to the same production database. Neither requires a code change,
a branch, or a PR — content is not code. (A *new* content type or field, e.g.
adding a document-attachment field to a page model, is a code change and
follows the normal [plan → branch → review → PR](../.claude/plans/README.md)
lifecycle instead.)

## Agent-driven path: how it works

The mechanism is Django's own management shell, run on the live Render
instance over SSH — the same Wagtail Python API
(`page.add_child()`, `revision.publish()`, `wagtaildocs.Document`) that
`apps/pipeline/models.py`'s `DailyReportPage` already uses internally to
auto-publish daily reports from a `DailyAggregate`. There is no bespoke
management command per task — the shell is generic; only the Python snippet
changes.

**Connection details** (service: `thandkoi-clinics`, id
`srv-d9ej48n41pts73f1i3p0`, Render workspace "Hikmatyar's workspace"):

```bash
ssh srv-d9ej48n41pts73f1i3p0@ssh.singapore.render.com \
  "cd /opt/render/project/src && uv run python manage.py shell -c \"<python>\""
```

This requires the operator's SSH public key registered under Render →
Account Settings → SSH Public Keys. Reusing an existing local keypair
(`~/.ssh/id_ed25519` or similar) is fine — only the public key is shared.

## Guardrails

This path writes directly to the production database with no draft/review
step of its own, so:

- **Read before you write.** Confirm IDs/state with a read-only query first
  (e.g. `Document.objects.get(title=...)`, `Page.objects.count()`) before
  running anything that calls `.save()`, `add_child()`, or `.publish()`.
- **Use Wagtail's own API, never raw SQL against page tables.** Wagtail
  pages are a treebeard tree (`path`/`depth`/`numchild` bookkeeping) plus
  revisions and search-index hooks — raw `INSERT`/`UPDATE` against
  `wagtailcore_page` (or similar) can silently corrupt the tree. Always go
  through `Page`/model methods.
- **Never fabricate field values.** If a required field's value isn't known
  (e.g. a date, a count), ask rather than guess or default it.
- **The CLAUDE.md privacy invariants still apply.** In particular: never
  write real patient data through this path, and never pass patient data to
  an AI call as part of a content operation.
- **Confirm before the write actually runs**, the same as any other
  production-affecting action — this doc describes the mechanism, not a
  blanket standing approval to run arbitrary writes unattended.

## Example: publishing a newsletter issue

`NewsletterPage` is the site's one archive content type — a medical camp is
published as an issue like any other, since Plan 21 (2026-08-10) retired the
separate `CampReportPage`. Use `issue_label` to keep the camp framing in the
masthead.

```python
from apps.core.models import NewsletterIndexPage, NewsletterPage

parent = NewsletterIndexPage.objects.first()

page = NewsletterPage(
    title="Free Sugar Camp",
    slug="free-sugar-camp",
    issue_date="2026-XX-XX",  # never fabricated — ask if unknown
    issue_label="Camp Report",  # masthead reads "AUGUST 2026 · CAMP REPORT"
    summary="A short teaser for the archive listing.",
    body=[
        ("paragraph", "<p>A short account of the camp.</p>"),
        (
            "stat_band",
            {"stats": [{"value": "379", "label": "patients seen"}]},
        ),
    ],
)
parent.add_child(instance=page)
page.save_revision().publish()
```

`body` is a StreamField, so an issue mixes prose with structured blocks —
`paragraph`, `photo`, `stat_band`, `highlights` and `feature_split`. A
`photo` block is consent-gated (`brand-guidelines.md` §5) and will refuse to
save unless `consent_confirmed` is ticked.

**Attaching a PDF.** `NewsletterPage` has no document field, deliberately.
Upload the file as a `wagtaildocs.Document` and link it from a `paragraph`
block instead:

```python
from wagtail.documents.models import Document

doc = Document.objects.get(title="Inauguration report")
# In a paragraph block's rich text:
#   <a linktype="document" id="{doc.id}">Download the report (PDF)</a>
```

That is how the inauguration report's PDF is reached today, from the "A new
chapter begins" issue — the only link to that document on the site.
