#!/usr/bin/env bash
# Push the current main to the PUBLIC repo as one new commit on top of public/main (T283).
#
#   scripts/publish_update.sh            build the commit, check it, push it to remote 'public'
#   scripts/publish_update.sh --dry-run  build and check, push nothing
#
# Run it after every deploy (deploy/deploy.sh). The private history stays on 'origin'.
# Steps:
#   1. Stop if the working tree has changes.
#   2. scripts/publish_check.sh on the tree. Stop on a hit.
#   3. git fetch public main. Stop (exit 0) if public/main already has the tree of HEAD.
#   4. One commit: the tree of HEAD, parent public/main, author Sveder.
#   5. A clone of that commit only, and publish_check.sh --strict-history there. Stop on a hit.
#   6. git push public <commit>:main (a fast-forward, never a force push).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

if [ -n "$(git status --porcelain)" ]; then
  echo "STOP: the working tree has changes. Commit or stash them first." >&2; exit 1
fi
git remote get-url public >/dev/null 2>&1 || { echo "STOP: no remote 'public'." >&2; exit 1; }

echo "== 1/4 publish check on the tree"
scripts/publish_check.sh >/dev/null || { echo "STOP: the publish check found a hit in the tree. Run scripts/publish_check.sh to see it." >&2; exit 1; }

echo "== 2/4 fetch public/main"
git fetch -q public main
TREE=$(git rev-parse "HEAD^{tree}")
if [ "$(git rev-parse "public/main^{tree}")" = "$TREE" ]; then
  echo "OK: public/main already has this tree. Nothing to push."; exit 0
fi

SRC=$(git rev-parse --short HEAD)
MSG="Update: $(git log -1 --format=%s HEAD | cut -c1-200)"
NEW=$(GIT_AUTHOR_NAME=Sveder GIT_AUTHOR_EMAIL=mikle3@gmail.com \
      GIT_COMMITTER_NAME=Sveder GIT_COMMITTER_EMAIL=mikle3@gmail.com \
      git commit-tree "$TREE" -p public/main -m "$MSG")
echo "== 3/4 new public commit $(git rev-parse --short "$NEW") (tree of $SRC)"

echo "== 4/4 strict history check on a clone of the public history"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git branch -f public-update "$NEW" >/dev/null
git clone -q --single-branch --branch public-update "$ROOT" "$TMP/pub"
git branch -D public-update >/dev/null
EXTRA=()
[ -f "$ROOT/.env" ] && EXTRA+=("$ROOT/.env")
( cd "$TMP/pub" && git remote remove origin && scripts/publish_check.sh --strict-history "${EXTRA[@]}" >/dev/null ) \
  || { echo "STOP: the public history has a hit. Nothing pushed." >&2; exit 1; }

if [ "$DRY" = 1 ]; then echo "Dry run: nothing pushed."; exit 0; fi
git push -q public "$NEW:refs/heads/main"
echo "OK: pushed $(git rev-parse --short "$NEW") to public main."
