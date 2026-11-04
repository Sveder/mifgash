"""F8c (T262): make or update the staff superuser for /ops/. Idempotent.

  manage.py ops_superuser --user <name> --password-env MIFGASH_OPS_PASSWORD
  printf '%s' "$PW" | manage.py ops_superuser --user <name> --password-stdin

The password never goes on the command line. An existing user gets the new password.
"""
import os
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the staff superuser for /ops/ (password from an env var or stdin)."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--password-env", default="")
        parser.add_argument("--password-stdin", action="store_true")

    def handle(self, *args, user, password_env, password_stdin, **kw):
        if password_stdin:
            pw = sys.stdin.read().strip()
        elif password_env:
            pw = os.environ.get(password_env, "")
        else:
            raise CommandError("give --password-env NAME or --password-stdin")
        if len(pw) < 16:
            raise CommandError("password missing or shorter than 16 characters")
        U = get_user_model()
        u, created = U.objects.get_or_create(username=user)
        u.is_staff = u.is_superuser = u.is_active = True
        u.set_password(pw)
        u.save()
        self.stdout.write(f"ops superuser '{user}' {'created' if created else 'updated'}")
