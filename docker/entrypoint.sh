#!/bin/sh
# Container start for the Mifgash compose stack.
#   web  : migrate, load the venue fixture, copy static files for nginx, run gunicorn on 8000
#   tick : run "manage.py tick" every 60 s (the server uses a systemd timer for the same job)
# Keys: if MIFGASH_SECRET_KEY / MIFGASH_FIELD_KEYS / MIFGASH_HASH_KEY are not set, random keys are made
# once and kept in the "keys" volume, so encrypted rows stay readable after a restart.
set -e
KEYS=/keys/keys.env
mkdir -p /keys
(
  flock 9
  if [ ! -s "$KEYS" ]; then
    python - > "$KEYS.tmp" <<'PY'
import secrets
from cryptography.fernet import Fernet
print("GEN_SECRET_KEY=" + secrets.token_urlsafe(48))
print("GEN_FIELD_KEYS=" + Fernet.generate_key().decode())
print("GEN_HASH_KEY=" + secrets.token_urlsafe(32))
PY
    mv "$KEYS.tmp" "$KEYS"
  fi
) 9>/keys/.lock
. "$KEYS"
export MIFGASH_SECRET_KEY="${MIFGASH_SECRET_KEY:-$GEN_SECRET_KEY}"
export MIFGASH_FIELD_KEYS="${MIFGASH_FIELD_KEYS:-$GEN_FIELD_KEYS}"
export MIFGASH_HASH_KEY="${MIFGASH_HASH_KEY:-$GEN_HASH_KEY}"

case "${1:-web}" in
  web)
    python manage.py migrate --noinput
    python manage.py import_venues --file planner/fixtures/osm_venues.json
    if [ -d /static ]; then cp -r /app/staticfiles/. /static/; fi
    exec gunicorn mifgash_site.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 90
    ;;
  tick)
    # wait for the web container to finish the migrations
    until python manage.py migrate --check >/dev/null 2>&1; do sleep 3; done
    while true; do
      python manage.py tick || echo "tick failed" >&2
      sleep 60
    done
    ;;
  *)
    exec "$@"
    ;;
esac
