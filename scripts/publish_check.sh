#!/usr/bin/env bash
# Publish check: run before the repo goes public.
# Looks for keys, private IPs, tailnet host names, phone numbers, home paths, WhatsApp ids,
# Hebrew text, bad tracked files (db, key, log, pyc, media over 200 kB) and private words in the working tree
# and in the full git history.
#
#   scripts/publish_check.sh [--strict-history] [extra.env ...]
#
# Exit 0: the working tree is clean. Exit 1: the working tree has a hit.
# A hit in the history only prints a WARN line, unless --strict-history is given.
#
# Literal secrets: every value of a *KEY*, *PASSWORD*, *SECRET* or *TOKEN* variable in .env,
# in $MIFGASH_META_ENV and in the extra env files is searched for as plain text.
# Private words (names, phone numbers, emails that must never be public): one per line in
# $MIFGASH_PRIVATE_WORDS (default ~/.config/mifgash/private-words.txt). That file lives
# outside the repo. A hit prints the file and line, never the word.
set -u
cd "$(dirname "$0")/.."

STRICT=0
ENV_FILES=(.env)
for a in "$@"; do
  if [ "$a" = "--strict-history" ]; then STRICT=1; else ENV_FILES+=("$a"); fi
done
[ -n "${MIFGASH_META_ENV:-}" ] && ENV_FILES+=("$MIFGASH_META_ENV")
WORDS="${MIFGASH_PRIVATE_WORDS:-$HOME/.config/mifgash/private-words.txt}"

EXCL=(--exclude-dir=.git --exclude-dir=.venv --exclude-dir=.venv-tts --exclude-dir=media --exclude-dir=__pycache__
      --exclude=.env --exclude='*.sqlite3' --exclude='*.pyc' --exclude=publish_check.sh)

# Private IPv4 ranges, tailnet names, private key blocks, cloud and API keys, live Mifgash agent keys,
# database URLs with a password, Israeli phone numbers, the droplet IP, home paths, WhatsApp JIDs.
PAT='\b(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3})\b|[a-z0-9-]+\.ts\.net|\btail[0-9a-f]{6}\b|BEGIN [A-Z ]*PRIVATE KEY|sk-ant-[A-Za-z0-9]|mif_[A-Za-z0-9_-]{20,}'
PAT+='|\b(AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
PAT+='|Bearer [A-Za-z0-9._~+/=-]{16,}|Api-Key [A-Za-z0-9._~+/=-]{12,}'
PAT+='|\b(postgres(ql)?|mysql|rediss?)://[^:/@[:space:]]+:[^@[:space:]]+@'
PAT+='|(\+972[ -]?|\b0)5[0-9][ -]?[0-9]{3}[ -]?[0-9]{4}\b'
PAT+='|\b104\.248\.40\.128\b|/home/[a-z_][a-z0-9_-]*/|\b[0-9]+@(lid|s\.whatsapp\.net)\b'

# Test data is allowed per MATCH, not per line: a match is skipped only when the match itself is
# a documentation host (example.*) or one of the made-up test values below.
ALLOW='^([a-z0-9-]*example[a-z0-9.-]*|10\.0\.0\.[59]|10\.1\.1\.1|10\.9\.9\.9|192\.168\.1\.20|100\.80\.1\.2|050-?0000000|\+972-?500000000)$'

# Hebrew letters: allowed only on SPEC.md line 3 (the name). Binary files (the font) are skipped by -I.
HEB='[\x{0590}-\x{05FF}]{2,}'
HEB_ALLOW_LINE=$(sed -n 3p SPEC.md 2>/dev/null)

tree_hits=0
hist_hits=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [ -z "${MIFGASH_META_ENV:-}" ]; then
  echo "WARN MIFGASH_META_ENV is unset; the Baseten key literal is not checked"
fi

git log -p --all --format='commit %h' > "$TMP/history"
# one row per added line: commit <TAB> +text
awk '/^commit [0-9a-f]+$/ {c=$2; next} /^\+/ {print c "\t" $0}' "$TMP/history" > "$TMP/added"

# commits that hold a line matched by grep options $@ in the history dump
hist_commits() {
  grep "$@" "$TMP/added" | cut -f1 | sort -u | tr '\n' ' '
}

# reads grep -n -o rows (<prefix>:<line>:<match>), drops allowed matches, prints the rest
drop_allowed() {
  awk -v allow="$ALLOW" '{ m = $0; sub(/^[^:]*:[^:]*:/, "", m); if (m !~ allow) print }'
}

# hide the value: keep 4 characters
mask() {
  awk '{ p = $0; sub(/:[^:]*$/, "", p); m = $0; sub(/^[^:]*:[^:]*:/, "", m); print p ": " substr(m, 1, 4) "..." }'
}

echo "== patterns: working tree"
grep -r -n -o -I -E "$PAT" "${EXCL[@]}" . | drop_allowed > "$TMP/t"
if [ -s "$TMP/t" ]; then
  mask < "$TMP/t"; tree_hits=$((tree_hits + $(wc -l < "$TMP/t")))
else echo "no hit"; fi

echo "== patterns: history"
# grep on one file prints <line>:<match>; the h: prefix gives drop_allowed its <file>:<line>: form (T283:
# without it no allowed test value was ever dropped in the history).
grep -n -o -E "$PAT" "$TMP/added" | sed 's/^/h:/' | drop_allowed | cut -d: -f2 > "$TMP/n"
c=$(awk -F'\t' 'NR==FNR {want[$1]; next} FNR in want {print $1}' "$TMP/n" "$TMP/added" | sort -u | tr '\n' ' ')
if [ -n "$c" ]; then echo "WARN added in commits: $c"; hist_hits=1; else echo "no hit"; fi

echo "== Hebrew text"
LC_ALL=C.UTF-8 grep -r -n -I -P "$HEB" "${EXCL[@]}" . \
  | awk -v ok="./SPEC.md:3:$HEB_ALLOW_LINE" '$0 != ok' | cut -d: -f1,2 > "$TMP/t"
if [ -s "$TMP/t" ]; then
  sed 's/^/Hebrew text in /' "$TMP/t"; tree_hits=$((tree_hits + $(wc -l < "$TMP/t")))
else echo "tree: no hit"; fi
c=$(cut -f2- "$TMP/added" | LC_ALL=C.UTF-8 grep -n -P "$HEB" | awk -v ok="+$HEB_ALLOW_LINE" '{l=$0; sub(/^[0-9]+:/, "", l); if (l != ok) {split($0, a, ":"); print a[1]}}' \
    | awk -F'\t' 'NR==FNR {want[$1]; next} FNR in want {print $1}' - "$TMP/added" | sort -u | tr '\n' ' ')
if [ -n "$c" ]; then echo "WARN history holds Hebrew text in commits: $c"; hist_hits=1; else echo "history: no hit"; fi

echo "== tracked files"
bad=$(git ls-files | grep -E '\.(sqlite3|db|pem|key|log|pyc)$|(^|/)\.coverage$' || true)
if [ -n "$bad" ]; then
  echo "$bad" | sed 's/^/tracked file type must not be public: /'; tree_hits=$((tree_hits + $(echo "$bad" | wc -l)))
fi
big=$(git ls-files -z | grep -z -i -E '\.(png|jpe?g|mp4|wav)$' | xargs -0 -r stat -c '%s %n' 2>/dev/null | awk '$1 > 204800 {print $2 " (" int($1/1024) " kB)"}')
if [ -n "$big" ]; then
  echo "$big" | sed 's/^/tracked media over 200 kB: /'; tree_hits=$((tree_hits + $(echo "$big" | wc -l)))
fi
[ -z "$bad$big" ] && echo "no hit"

echo "== literal secret values from: ${ENV_FILES[*]}"
: > "$TMP/values"
for f in "${ENV_FILES[@]}"; do
  [ -r "$f" ] || { echo "skip $f (not readable)"; continue; }
  sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?[A-Z0-9_]*(KEY|PASSWORD|SECRET|TOKEN)[A-Z0-9_]*=//p' "$f" \
    | sed -E "s/^[\"']//; s/[\"']\$//" | awk 'length($0) >= 8' >> "$TMP/values"
done
if [ -s "$TMP/values" ]; then
  echo "$(wc -l < "$TMP/values") values"
  if grep -r -l -I -F -f "$TMP/values" "${EXCL[@]}" . > "$TMP/t"; then
    sed 's/^/tree hit in /' "$TMP/t"; tree_hits=$((tree_hits + 1))
  fi
  c=$(hist_commits -F -f "$TMP/values")
  if [ -n "$c" ]; then echo "WARN history holds a secret value in commits: $c"; hist_hits=1; fi
else echo "no values found"; fi

echo "== private words from $WORDS"
if [ -s "$WORDS" ]; then
  if grep -r -n -I -i -w -F -f "$WORDS" "${EXCL[@]}" . | cut -d: -f1,2 > "$TMP/t" && [ -s "$TMP/t" ]; then
    sed 's/^/private word hit in /' "$TMP/t"; tree_hits=$((tree_hits + $(wc -l < "$TMP/t")))
  else echo "tree: no hit"; fi
  c=$(hist_commits -i -w -F -f "$WORDS")
  if [ -n "$c" ]; then echo "WARN history holds a private word in commits: $c"; hist_hits=1
  else echo "history: no hit"; fi
else
  echo "WARN no private words file; names were not checked"
fi

echo "== .gitignore"
for g in .env server.md '*.sqlite3' .venv/; do
  grep -q -x -F "$g" .gitignore || { echo "missing in .gitignore: $g"; tree_hits=$((tree_hits + 1)); }
done
tracked=$(git ls-files | grep -E '(^|/)(\.env|server\.md)$|\.sqlite3$|^\.venv/' || true)
[ -n "$tracked" ] && { echo "tracked but must not be: $tracked"; tree_hits=$((tree_hits + 1)); }

echo "== result: working tree hits $tree_hits, history warnings $hist_hits"
[ "$tree_hits" -eq 0 ] || exit 1
[ "$STRICT" -eq 1 ] && [ "$hist_hits" -ne 0 ] && exit 1
exit 0
