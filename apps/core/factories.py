"""
factory_boy factories for core models.

Wagtail pages live in a tree, so they can't be created with a plain
``Model.objects.create(...)`` — a new page must be added under a parent via
``parent.add_child(instance=...)``. This factory encapsulates that so tests in
this and later plans have one consistent pattern to follow.
"""

import factory
from wagtail.models import Page

from apps.core.models import HomePage


class HomePageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HomePage

    title = factory.Sequence(lambda n: f"Home {n}")
    slug = factory.Sequence(lambda n: f"home-{n}")
    intro = "<p>Welcome to The Thandkoi Clinics.</p>"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Attach the new page under an explicit parent (default: tree root)."""
        parent = kwargs.pop("parent", None) or Page.get_first_root_node()
        instance = model_class(*args, **kwargs)
        parent.add_child(instance=instance)
        return instance
