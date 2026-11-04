#!/usr/bin/env python3
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    # Run under the project venv (psycopg, cryptography live there), also when called as `python3 manage.py`.
    venv = Path(__file__).resolve().parent / ".venv"
    if (venv / "bin" / "python").exists() and Path(sys.prefix).resolve() != venv.resolve():
        os.execv(str(venv / "bin" / "python"), [str(venv / "bin" / "python"), *sys.argv])
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mifgash_site.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
