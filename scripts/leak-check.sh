#!/usr/bin/env bash
# leak-check.sh — stop private references (home paths, LAN/tailnet IPs, session ids,
# e-mail addresses, credentials, non-English prose) from reaching a public repository.
#
#   scripts/leak-check.sh staged [--quiet]   # pre-commit: scans the staged blobs only
#   scripts/leak-check.sh all    [--quiet]   # CI / manual: scans every tracked file
#
# --quiet prints path:line: [rule] without the matching text. It is implied when $CI is
# set, so a public CI log never echoes the thing that leaked.
#
# Rules: generic patterns live in this file. Private ones (your hostnames, usernames,
# project code names) go in .leak-patterns.local — one extended regex per line, `#`
# comments allowed, matched case-insensitively. That file must stay gitignored; the
# check fails when it is tracked or not ignored.
#
# A line that must legitimately contain a pattern (for example docs that describe the
# rules) carries the marker `leak-allow` anywhere on the line.
#
# Exit: 0 clean · 1 findings · 2 usage or setup error
# Works with bash 3.2 and BSD grep (macOS) as well as GNU tools.

set -u

MODE=""
QUIET=${CI:+1}
for arg in "$@"; do
  case "$arg" in
    staged|all) MODE=$arg ;;
    --quiet) QUIET=1 ;;
    -h|--help)
      awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
      exit 0 ;;
    *) echo "leak-check: unknown argument: $arg" >&2; exit 2 ;;
  esac
done
if [ -z "$MODE" ]; then
  echo "usage: scripts/leak-check.sh staged|all [--quiet]" >&2
  exit 2
fi

if ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  IN_GIT=1
else
  ROOT=$(pwd)
  IN_GIT=""
fi
cd "$ROOT" || exit 2

if [ "$MODE" = staged ] && [ -z "$IN_GIT" ]; then
  echo "leak-check: staged mode needs a git repository" >&2
  exit 2
fi

SELF="scripts/leak-check.sh"
LOCAL_FILE=".leak-patterns.local"
ALLOW_MARKER="leak-allow"
# UTF-8 lead bytes of U+0E00..U+0E7F (Thai). Matched with LC_ALL=C so GNU and BSD grep agree.
THAI_BYTES=$(printf '\xe0[\xb8\xb9]')

OUT=$(mktemp "${TMPDIR:-/tmp}/leak-check.XXXXXX") || exit 2
trap 'rm -f "$OUT"' EXIT

# ---------------------------------------------------------------------------
# Generic rules. Fields are TAB separated: name, exempt-path ERE ("-" = none), grep
# flags ("-" = none), pattern. Patterns are EREs evaluated under LC_ALL=C.
# ---------------------------------------------------------------------------
generic_rules() {
  printf '%s\t%s\t%s\t%s\n' \
    'abs-home-path' '-' '-' \
      '(^|[^A-Za-z0-9_])/(Users|home)/[A-Za-z0-9_.-]+'
  printf '%s\t%s\t%s\t%s\n' \
    'private-ip' '-' '-' \
      '(^|[^0-9.])(192\.168\.[0-9]{1,3}\.[0-9]{1,3}|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3})([^0-9.]|$)'
  printf '%s\t%s\t%s\t%s\n' \
    'uuid' '-' '-' \
      '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
  printf '%s\t%s\t%s\t%s\n' \
    'email' '^(LICENSE|CODE_OF_CONDUCT\.md|SECURITY\.md|\.claude-plugin/(plugin|marketplace)\.json)$' '-' \
      '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}'
  printf '%s\t%s\t%s\t%s\n' \
    'credential' '-' '-' \
      '(sk-ant-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|op://|eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,})'
  printf '%s\t%s\t%s\t%s\n' \
    'thai-script' '\.th\.md$' '-' \
      "$THAI_BYTES"
}

# Private rules from .leak-patterns.local: one ERE per line, case-insensitive.
local_rules() {
  [ -f "$LOCAL_FILE" ] || return 0
  n=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|'#'*) continue ;;
    esac
    n=$((n + 1))
    printf 'local:%s\t-\t-i\t%s\n' "$n" "$line"
  done < "$LOCAL_FILE"
}

content_of() {
  if [ "$MODE" = staged ]; then
    git show ":$1" 2>/dev/null
  else
    cat -- "$1"
  fi
}

# scan_file PATH — appends findings for every applicable rule to $OUT.
scan_file() {
  f=$1
  while IFS="$(printf '\t')" read -r name exempt flags pattern; do
    [ -n "$name" ] || continue
    if [ "$exempt" != "-" ] && printf '%s\n' "$f" | LC_ALL=C grep -qE -- "$exempt"; then
      continue
    fi
    if [ "$flags" = "-" ]; then
      content_of "$f" | LC_ALL=C grep -nIE -- "$pattern"
    else
      content_of "$f" | LC_ALL=C grep -nIE "$flags" -- "$pattern"
    fi 2>/dev/null \
      | grep -vF -- "$ALLOW_MARKER" \
      | awk -v f="$f" -v r="$name" -v q="$QUIET" '{
          i = index($0, ":"); n = substr($0, 1, i - 1); t = substr($0, i + 1)
          if (q != "") print f ":" n ": [" r "]"
          else         print f ":" n ": [" r "] " substr(t, 1, 160)
        }' >> "$OUT"
  done <<EOF
$(generic_rules; local_rules)
EOF
}

# ---------------------------------------------------------------------------
# Setup checks: the private pattern file must never be committed.
# ---------------------------------------------------------------------------
if [ -n "$IN_GIT" ] && [ -f "$LOCAL_FILE" ] && ! git check-ignore -q -- "$LOCAL_FILE"; then
  printf '%s:0: [setup] %s exists but is not gitignored — add it to .gitignore\n' \
    "$LOCAL_FILE" "$LOCAL_FILE" >> "$OUT"
fi

# ---------------------------------------------------------------------------
# File list.
# ---------------------------------------------------------------------------
list_files() {
  if [ "$MODE" = staged ]; then
    git diff --cached --name-only --diff-filter=ACMR -z
  elif [ -n "$IN_GIT" ]; then
    git ls-files -z
  else
    find . -type f ! -path './.git/*' -print0
  fi
}

nfiles=0
while IFS= read -r -d '' f; do
  f=${f#./}
  case "$f" in
    "$SELF") continue ;;
    "$LOCAL_FILE")
      # Outside git nothing is "tracked": the file is simply not scanned.
      if [ -n "$IN_GIT" ]; then
        printf '%s:0: [setup] private pattern file is tracked/staged — unstage it and gitignore it\n' "$f" >> "$OUT"
      fi
      continue ;;
  esac
  nfiles=$((nfiles + 1))
  scan_file "$f"
done < <(list_files)

# ---------------------------------------------------------------------------
# Report.
# ---------------------------------------------------------------------------
count=$(wc -l < "$OUT" | tr -d ' ')
if [ "$count" -gt 0 ]; then
  cat "$OUT"
  echo "leak-check: $count finding(s) in mode=$MODE ($nfiles file(s) scanned)." >&2
  echo "leak-check: fix the line, or append the marker '$ALLOW_MARKER' when it is intentional." >&2
  exit 1
fi
echo "leak-check: clean (mode=$MODE, $nfiles file(s) scanned)"
exit 0
