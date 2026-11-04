"""F8c (T262): every planner model in the Django admin at /ops/admin/. Encrypted fields are read-only."""
from django.apps import apps
from django.contrib import admin

from .crypto import EncryptedTextField

SECRET_HASHES = {"key_hash", "token_hash", "token", "email_digest"}


def _admin_for(model):
    enc = [f.name for f in model._meta.fields if isinstance(f, EncryptedTextField)]
    hashes = [f.name for f in model._meta.fields if f.name in SECRET_HASHES]
    names = [f.name for f in model._meta.fields
             if f.name not in enc and f.name not in hashes and not f.is_relation][:8]
    attrs = {"readonly_fields": enc + hashes, "list_display": names or ["__str__"],
             "ordering": ["-pk"], "list_per_page": 100}
    return type(f"{model.__name__}Admin", (admin.ModelAdmin,), attrs)


for _model in apps.get_app_config("planner").get_models():
    if not admin.site.is_registered(_model):
        admin.site.register(_model, _admin_for(_model))
