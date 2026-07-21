"""URLs registered into the Wagtail admin (see ``wagtail_hooks.py``)."""

from django.urls import path

from apps.pipeline import admin_views

app_name = "pipeline"

urlpatterns = [
    path("upload/", admin_views.upload_export, name="upload_export"),
]
