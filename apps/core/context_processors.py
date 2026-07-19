"""
Context processors exposing operational config to every template.

Contact and bank details are configuration, not content — they're read from
environment variables (see ORG_* settings in config/settings/base.py) rather
than hardcoded in a template, matching the architecture brief's "contact and
bank details are configured in the running application, not stored in this
repository". A later plan (05, Donate) may move these into a proper
Wagtail-editable settings model once there's real bank-detail content to
manage; a context processor is enough for Plan 03's placeholder footer.
"""

from django.conf import settings


def org_contact(request):
    """Footer placeholders: contact, bank/Zakat details, and social links."""
    return {
        "ORG_CONTACT_EMAIL": settings.ORG_CONTACT_EMAIL,
        "ORG_CONTACT_PHONE": settings.ORG_CONTACT_PHONE,
        "ORG_BANK_DETAILS": settings.ORG_BANK_DETAILS,
        "ORG_SOCIAL_LINKS": settings.ORG_SOCIAL_LINKS,
    }
