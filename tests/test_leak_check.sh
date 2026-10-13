#!/usr/bin/env bash
# Tests for scripts/leak-check.sh: every rule, the exemptions, the leak-allow marker,
# quiet/CI output, staged vs working tree, the .leak-patterns.local setup checks and the
# exit codes. Run it with the bash under test, e.g. on macOS: /bin/bash tests/test_leak_check.sh
#
# Fixture strings are assembled from pieces ("/Use""rs") so that this file itself passes
# leak-check in `all` mode: the rule must fire on the fixture, not on the test source.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/scripts/leak-check.sh"
SH=${BASH:-bash}                       # the bash running this test runs the script too
T=$(mktemp -d "${TMPDIR:-/tmp}/lc-test.XXXXXX")
trap 'rm -rf "$T"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@localhost GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@localhost

fail=0
ok()  { echo "  ok   $1"; }
bad() { echo "  FAIL $1"; fail=$((fail + 1)); }
expect_rule() { grep -q "\[$2\]" "$1" && ok "flags $2" || bad "missing rule $2"; }
expect_no()   { grep -q -- "$2" "$1" && bad "should not flag: $2" || ok "ignores $2"; }

# --- fixture pieces (split so this source file stays clean) ---------------------------
HOME_PATH="/Use""rs/alice/src"
LAN_IP="192.168.""1.10"
TAILNET_IP="100.70.""1.2"
UUID="12345678-1234-1234-1234-""123456789abc"
MAIL="bob@""example.com"
LIC_MAIL="alice@""example.com"
GHP="ghp_$(printf 'a%.0s' $(seq 1 24))"
AKIA="AKIA""ABCDEFGHIJKLMNOP"
THAI=$(printf '\xe0\xb8\x81\xe0\xb8\x82')      # two Thai letters, U+0E01 U+0E02

mk_fixtures() {   # $1 = dir
  mkdir -p "$1/scripts" "$1/.claude-plugin"
  cp "$SRC" "$1/scripts/leak-check.sh"; chmod +x "$1/scripts/leak-check.sh"
  cat > "$1/a.md" <<EOF
see $HOME_PATH for the layout
host at $LAN_IP and node $TAILNET_IP
session $UUID
contact $MAIL
token $GHP
key $AKIA
$THAI this line is thai
documented: paths like $HOME_PATH are flagged  leak-allow
plain ip 100.1.2.3 and 8.8.8.8 are fine
install with /plugin install relay@acme-market
placeholder <you>@example.com and /home/<user> are fine
EOF
  printf '%s in this file is fine\n' "$THAI" > "$1/README.th.md"
  printf 'Copyright (c) 2026 Alice <%s>\n' "$LIC_MAIL" > "$1/LICENSE"
  printf '{"name":"relay","author":{"email":"%s"}}\n' "$LIC_MAIL" > "$1/.claude-plugin/plugin.json"
  printf 'lives on ACME-Internal-Host today\n' > "$1/b.txt"
  printf '# private names\nacme-internal-host\n\n' > "$1/.leak-patterns.local"
  printf 'nothing here\n' > "$1/clean.txt"
}
run_lc() {   # $1 = dir, rest = args
  d=$1; shift
  ( cd "$d" && "$SH" scripts/leak-check.sh "$@" )
}

echo "== non-git all mode =="
mk_fixtures "$T/plain"
run_lc "$T/plain" all > "$T/out1" 2>&1; rc=$?
[ $rc -eq 1 ] && ok "exit 1 with findings" || bad "exit $rc (want 1)"
for r in abs-home-path private-ip uuid email credential thai-script local:1; do expect_rule "$T/out1" "$r"; done
expect_no "$T/out1" "README.th.md"
expect_no "$T/out1" "^LICENSE"
expect_no "$T/out1" "plugin.json"
expect_no "$T/out1" "a.md:8:"
expect_no "$T/out1" "100.1.2.3"
expect_no "$T/out1" "relay@acme"
expect_no "$T/out1" "<you>@"
expect_no "$T/out1" "/home/<user>"
expect_no "$T/out1" "scripts/leak-check.sh:"
expect_no "$T/out1" "\.leak-patterns\.local"
n=$(grep -c '\[private-ip\]' "$T/out1");  [ "$n" -eq 1 ] && ok "one private-ip line" || bad "private-ip lines=$n"
n=$(grep -c '\[credential\]' "$T/out1");  [ "$n" -eq 2 ] && ok "two credential lines" || bad "credential lines=$n"

echo "== quiet mode hides the text =="
run_lc "$T/plain" all --quiet > "$T/out1q" 2>&1
grep -q 'alice' "$T/out1q" && bad "quiet leaks text" || ok "quiet hides text"
( cd "$T/plain" && CI=1 "$SH" scripts/leak-check.sh all ) > "$T/out1c" 2>&1
grep -q 'alice' "$T/out1c" && bad "CI leaks text" || ok "CI implies quiet"

echo "== clean tree exits 0 =="
mkdir -p "$T/clean/scripts"; cp "$SRC" "$T/clean/scripts/"; printf 'hello\n' > "$T/clean/x.md"
run_lc "$T/clean" all > "$T/out2" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "exit 0 clean" || { bad "exit $rc"; cat "$T/out2"; }

echo "== staged mode =="
mk_fixtures "$T/repo"
( cd "$T/repo" && git init -q && git add -A ) || bad "git init/add"
run_lc "$T/repo" staged > "$T/out3" 2>&1; rc=$?
[ $rc -eq 1 ] && ok "staged exit 1" || bad "staged exit $rc"
grep -q '\[setup\].*tracked/staged' "$T/out3" && ok "flags staged .leak-patterns.local" || bad "missing tracked/staged setup finding"
grep -q 'not gitignored' "$T/out3" && ok "flags missing .gitignore" || bad "missing gitignore setup finding"
expect_rule "$T/out3" "local:1"
( cd "$T/repo" && git rm -q --cached .leak-patterns.local && printf '.leak-patterns.local\n' > .gitignore \
  && git add .gitignore && git rm -q --cached a.md b.txt ) || bad "git fixups"
run_lc "$T/repo" staged > "$T/out4" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "staged clean after fixes (exit 0)" || { bad "staged exit $rc"; cat "$T/out4"; }
# a working-tree-only edit must not be scanned in staged mode
( cd "$T/repo" && git commit -qm init && printf 'oops %s\n' "$HOME_PATH" >> clean.txt ) || bad "git commit"
run_lc "$T/repo" staged > "$T/out5" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "unstaged edit ignored" || { bad "unstaged edit scanned (exit $rc)"; cat "$T/out5"; }
( cd "$T/repo" && git add clean.txt )
run_lc "$T/repo" staged > "$T/out6" 2>&1; rc=$?
[ $rc -eq 1 ] && ok "staged edit caught" || bad "staged edit missed (exit $rc)"

echo "== git all mode scans tracked files only =="
( cd "$T/repo" && git reset -q && git checkout -q -- clean.txt )
run_lc "$T/repo" all > "$T/out7" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "tracked files clean, untracked a.md ignored" || { bad "git all exit $rc"; cat "$T/out7"; }

echo "== usage =="
run_lc "$T/clean" > /dev/null 2>&1;        [ $? -eq 2 ] && ok "no mode: exit 2" || bad "no mode exit"
run_lc "$T/clean" staged > /dev/null 2>&1; [ $? -eq 2 ] && ok "staged outside git: exit 2" || bad "staged outside git"
run_lc "$T/clean" --help | grep -q 'pre-commit' && ok "--help prints the header" || bad "--help"

echo
if [ $fail -eq 0 ]; then
  echo "ALL PASS ($("$SH" --version | head -1))"
else
  echo "FAILURES: $fail"
fi
exit $fail
