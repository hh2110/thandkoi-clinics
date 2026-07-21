"""Draft the monthly newsletter — Plan 09's one manual trigger.

Maintainer decision (PR #17, ``.claude/plans/09-ai-monthly-newsletter.md``
"Monthly trigger mechanism"): an Administrator runs this by hand at
month-end; there is no scheduled/cron job. Every run produces a
``NewsletterDraftRun`` audit row, visible in the Wagtail admin's "Newsletter
draft runs" listing — on success, an **unpublished** ``NewsletterPage``
revision an Administrator must review and publish; on failure, no draft at
all (see ``apps.pipeline.newsletter_drafting`` for why this is the opposite
of Plan 08's daily page).

Admin notes are a file prepared outside the platform (maintainer decision,
PR #17) — passed as a local path, since an Administrator runs this command
directly rather than through a web form. Photos can be picked from the
existing consent-gated Gallery (``--gallery-image``) or uploaded directly
(``--photo``); any directly-uploaded photo requires ``--confirm-consent``
for the whole run, since Plan 06's convention requires confirmed consent
before an identifiable photo can appear in a published page::

    uv run python manage.py draft_monthly_newsletter --month 2026-07 \\
        --notes notes.md \\
        --gallery-image 3 --gallery-image 7 \\
        --photo path/to/new.jpg:"Camp day handout" \\
        --confirm-consent --triggered-by administrator
"""

from __future__ import annotations

import datetime
import os

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from wagtail.images.models import Image

from apps.core.models import GalleryImage
from apps.pipeline.models import NewsletterDraftRun
from apps.pipeline.newsletter_drafting import (
    NewsletterPhotoInput,
    draft_monthly_newsletter,
)


class Command(BaseCommand):
    help = "Draft the monthly newsletter as an unpublished NewsletterPage revision."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month", required=True, help="Target calendar month, YYYY-MM."
        )
        parser.add_argument(
            "--notes",
            dest="notes_path",
            help="Path to a text/Markdown file of the admin's monthly notes.",
        )
        parser.add_argument(
            "--gallery-image",
            dest="gallery_image_ids",
            action="append",
            type=int,
            default=[],
            help="Existing consent-gated GalleryImage id to include (repeatable).",
        )
        parser.add_argument(
            "--photo",
            dest="photos",
            action="append",
            default=[],
            help="path/to/image.jpg[:caption] to upload directly for this "
            "issue (repeatable). Requires --confirm-consent.",
        )
        parser.add_argument(
            "--confirm-consent",
            action="store_true",
            help="Required if any --photo is given: confirms every "
            "identifiable person in the directly-uploaded photos has "
            "consented to publication (brand-guidelines.md §5).",
        )
        parser.add_argument(
            "--triggered-by",
            dest="username",
            help="Username of the Administrator running this, recorded on "
            "the audit row.",
        )

    def handle(self, *args, **options):
        try:
            month = datetime.datetime.strptime(options["month"], "%Y-%m").date()
        except ValueError as exc:
            raise CommandError(f"Invalid --month (expected YYYY-MM): {exc}") from exc

        notes_text = ""
        if options["notes_path"]:
            try:
                with open(options["notes_path"], encoding="utf-8") as fh:
                    notes_text = fh.read()
            except OSError as exc:
                raise CommandError(f"Could not read --notes file: {exc}") from exc

        if options["photos"] and not options["confirm_consent"]:
            raise CommandError(
                "--photo requires --confirm-consent — every identifiable "
                "person in a directly-uploaded photo must have consented "
                "before it can appear in a published page "
                "(brand-guidelines.md §5)."
            )

        photo_inputs = self._gallery_photo_inputs(
            options["gallery_image_ids"]
        ) + self._uploaded_photo_inputs(options["photos"])

        triggered_by = None
        if options["username"]:
            try:
                triggered_by = get_user_model().objects.get(
                    username=options["username"]
                )
            except get_user_model().DoesNotExist as exc:
                raise CommandError(f"No such user: {options['username']}") from exc

        run = draft_monthly_newsletter(
            month,
            notes_text=notes_text,
            photos=photo_inputs,
            triggered_by=triggered_by,
        )

        if run.status == NewsletterDraftRun.STATUS_SUCCEEDED:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Draft created: {run.newsletter_page} (unpublished) — "
                    "review and publish it in /admin/."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"No draft created for {month:%Y-%m}: {run.error_message}"
                )
            )

    def _gallery_photo_inputs(self, gallery_image_ids) -> list[NewsletterPhotoInput]:
        inputs = []
        for gallery_id in gallery_image_ids:
            try:
                gallery_image = GalleryImage.objects.select_related("image").get(
                    pk=gallery_id, consent_confirmed=True, image__isnull=False
                )
            except GalleryImage.DoesNotExist as exc:
                raise CommandError(
                    f"No consent-confirmed gallery image with id {gallery_id}."
                ) from exc
            inputs.append(
                NewsletterPhotoInput(
                    image=gallery_image.image,
                    caption=gallery_image.caption,
                    alt_text=gallery_image.alt_text,
                    consent_confirmed=True,
                )
            )
        return inputs

    def _uploaded_photo_inputs(self, photo_specs) -> list[NewsletterPhotoInput]:
        inputs = []
        for spec in photo_specs:
            path, _, caption = spec.partition(":")
            title = os.path.basename(path)
            try:
                with open(path, "rb") as fh:
                    image = Image.objects.create(title=title, file=File(fh, name=title))
            except OSError as exc:
                raise CommandError(
                    f"Could not read --photo file {path!r}: {exc}"
                ) from exc
            inputs.append(
                NewsletterPhotoInput(
                    image=image,
                    caption=caption,
                    alt_text=caption,
                    consent_confirmed=True,
                )
            )
        return inputs
