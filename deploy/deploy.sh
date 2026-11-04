#!/usr/bin/env bash
# Deploy the current main to the public host. Idempotent. One-time setup: README "Public deploy".
#   deploy/deploy.sh            (needs MIFGASH_SSH_KEY and MIFGASH_SSH_HOST, for example user@host)
set -euo pipefail
cd "$(dirname "$0")/.."
: "${MIFGASH_SSH_KEY:?}" "${MIFGASH_SSH_HOST:?}"
export GIT_SSH_COMMAND="ssh -i $MIFGASH_SSH_KEY -o BatchMode=yes"
git push "ssh://$MIFGASH_SSH_HOST/srv/www/mifgash/app" main:main
# Optional (T262): MIFGASH_OPS_PASSWORD makes or updates the /ops/ staff user MIFGASH_OPS_USER (required
# with the password, no default). The password travels inside the ssh stdin script, never on a command line.
{
if [ -n "${MIFGASH_OPS_PASSWORD:-}" ]; then
  : "${MIFGASH_OPS_USER:?MIFGASH_OPS_USER is required with MIFGASH_OPS_PASSWORD}"
  printf 'OPS_USER=%q\nOPS_PW=%q\n' "$MIFGASH_OPS_USER" "$MIFGASH_OPS_PASSWORD"
fi
cat <<'REMOTE'
set -euo pipefail
cd /srv/www/mifgash
venv/bin/pip install -q -r app/requirements.txt
run() { sudo -u mifgash bash -c 'set -a; . /srv/www/mifgash/mifgash.env; set +a; cd /srv/www/mifgash/app; exec ../venv/bin/python manage.py "$@"' _ "$@"; }
run migrate --noinput -v 0
run collectstatic --noinput -v 0
# T265: the OSM venue list from the committed fixture (no Overpass call on the droplet); idempotent
run import_venues --file planner/fixtures/osm_venues.json
if [ -n "${OPS_PW:-}" ]; then printf '%s' "$OPS_PW" | run ops_superuser --user "$OPS_USER" --password-stdin; fi
unset OPS_PW
sudo install -m 644 app/deploy/mifgash.service app/deploy/mifgash-tick.service app/deploy/mifgash-tick.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mifgash
sleep 3
systemctl is-active mifgash
curl -s -o /dev/null -w 'local %{http_code}\n' -H 'Host: mifgash.sveder.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8098/
REMOTE
} | ssh -i "$MIFGASH_SSH_KEY" -o BatchMode=yes "$MIFGASH_SSH_HOST" 'bash -s'
