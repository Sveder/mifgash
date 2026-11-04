#!/usr/bin/env bash
# Make the one-commit public history from the clean tree (T156, security review M2).
#
#   scripts/squash_for_public.sh            build and check the branch 'public', push nothing
#   scripts/squash_for_public.sh --push R   also push 'public' as 'main' to the remote R
#
# DO NOT run this before the publish day. The dated private history is the proof that the work
# was done during the hackathon. Keep the private repo (rename it, keep it private) as that proof.
#
# Steps:
#   1. Stop if the working tree has changes.
#   2. scripts/publish_check.sh on the tree. Stop on a hit.
#   3. A git bundle of the full private history, OUTSIDE the repo (../mifgash-private-<date>.bundle).
#   4. An orphan branch 'public' with ONE commit: the tracked files of HEAD.
#   5. A single-branch clone of 'public' in a temp dir, and publish_check.sh --strict-history there.
#      Exit 1 if the one commit holds a private word, an IP, a tailnet name or a key.
#   6. With --push R: git push R public:main. Push to a NEW, EMPTY repo. A force push over the old
#      repo is not enough: GitHub keeps old commits readable by their SHA.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PUSH=""
if [ "${1:-}" = "--push" ]; then PUSH="${2:?--push needs a remote name or URL}"; fi

if [ -n "$(git status --porcelain)" ]; then
  echo "STOP: the working tree has changes. Commit or stash them first." >&2; exit 1
fi
echo "== 1/4 publish check on the tree"
scripts/publish_check.sh || { echo "STOP: the publish check found a hit in the tree." >&2; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S)
BUNDLE="$ROOT/../mifgash-private-$STAMP.bundle"
echo "== 2/4 private history bundle: $BUNDLE"
git bundle create "$BUNDLE" --all

SRC=$(git rev-parse --short HEAD)
FIRST=$(git log -1 --format='%ad' --date=short "$(git rev-list --max-parents=0 HEAD | tail -1)")
LAST=$(git log -1 --format='%ad' --date=short)
echo "== 3/4 one-commit branch 'public' from $SRC"
git branch -D public >/dev/null 2>&1 || true
TREE=$(git rev-parse "HEAD^{tree}")
# MIFGASH_PUBLIC_MSG replaces the default message (T283 used it for the first public commit).
DEFAULT_MSG="Mifgash: entry for the Meta Global AI Developer Hackathon

Built during the event, $FIRST to $LAST. One squashed commit of the private
working history (private repo commit $SRC)."
MSG="${MIFGASH_PUBLIC_MSG:-$DEFAULT_MSG}"
NEW=$(GIT_AUTHOR_NAME=Sveder GIT_AUTHOR_EMAIL=mikle3@gmail.com \
      GIT_COMMITTER_NAME=Sveder GIT_COMMITTER_EMAIL=mikle3@gmail.com \
      git commit-tree "$TREE" -m "$MSG")
git branch public "$NEW"

echo "== 4/4 strict history check on a clone of 'public' only"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone -q --single-branch --branch public "$ROOT" "$TMP/pub"
EXTRA=()
[ -f "$ROOT/.env" ] && EXTRA+=("$ROOT/.env")
( cd "$TMP/pub" && git remote remove origin && scripts/publish_check.sh --strict-history "${EXTRA[@]}" ) \
  || { echo "STOP: the one commit has a hit. Branch 'public' stays local; fix the tree and run again." >&2; exit 1; }
echo "OK: branch 'public' = 1 commit ($(git rev-parse --short public)), tree of $SRC, checks pass."

if [ -n "$PUSH" ]; then
  echo "Pushing public -> $PUSH main"
  git push "$PUSH" public:main
else
  echo "Nothing pushed. To publish: make a NEW empty GitHub repo, then"
  echo "  scripts/squash_for_public.sh --push <new repo URL>"
fi
