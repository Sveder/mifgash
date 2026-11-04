"""Encryption at rest for sensitive fields, and hashing for secrets we only need to compare.

- EncryptedTextField: Fernet (AES-128-CBC + HMAC-SHA256). Keys come from MIFGASH_FIELD_KEYS,
  comma separated, newest first, so a key can rotate. The column holds 'enc1:<token>'; psql shows
  no plain text.
- digest(): keyed HMAC-SHA256 (MIFGASH_HASH_KEY). Use it for lookups on an encrypted value
  (find a user by email) and for agent API keys, which are stored hashed only.
"""
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "enc1:"


def _fernet():
    keys = [k.strip() for k in settings.FIELD_KEYS.split(",") if k.strip()]
    if not keys:
        raise ImproperlyConfigured("MIFGASH_FIELD_KEYS is empty; put a Fernet key in .env")
    return MultiFernet([Fernet(k) for k in keys])


def encrypt(text):
    return PREFIX + _fernet().encrypt(text.encode()).decode()


def decrypt(stored):
    if not stored.startswith(PREFIX):
        raise ValueError("value is not encrypted")
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken as e:
        raise ValueError("cannot decrypt: wrong MIFGASH_FIELD_KEYS") from e


def digest(text):
    key = settings.HASH_KEY
    if not key:
        raise ImproperlyConfigured("MIFGASH_HASH_KEY is empty; put a random key in .env")
    return hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()


class EncryptedTextField(models.TextField):
    """A text field that is encrypted in the database. Empty string stays empty (no secret in it).

    You cannot filter on it: the ciphertext changes on every save. Keep a digest() column for lookups.
    """

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return encrypt(str(value))

    def get_lookup(self, lookup_name):
        # Only isnull: an 'exact' match on ciphertext never hits, so a silent wrong answer is worse.
        if lookup_name != "isnull":
            return None
        return super().get_lookup(lookup_name)
