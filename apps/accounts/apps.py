"""App config for accounts & roles (Plan 07).

This app deliberately has no user-facing models. Its whole job is the
**Administrator** group and the one custom permission Plan 08's upload view
needs — see ``models.py`` and the migrations for why each exists.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts & roles"
