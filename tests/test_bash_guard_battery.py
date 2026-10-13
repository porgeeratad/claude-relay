#!/usr/bin/env python3
"""Behavioural battery for hooks/bash_guard.py: realistic commands an agent types, each
with the decision we expect. test_bash_guard.py checks the rule ids; this file checks
the *shape* of everyday usage — bypasses the guard must catch, and idioms it must not
block. Add a row here whenever a false positive or a bypass is found in the wild.

Run: python3 tests/test_bash_guard_battery.py
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import bash_guard  # noqa: E402

# (command, note)
DENY = [
    # --- S8: secret files, direct readers ---
    ("cat .env", "secret file"),
    ("cat .env.production", "secret file variant"),
    ("cat .envrc", "direnv file exports tokens"),
    ("cat .env*", "glob"),
    ("cat ./.env", "relative path"),
    ('cat "$HOME/.env"', "quoted path survives unquoting"),
    ("cat -- .env", "double dash"),
    ("cat -A .env", "cat option"),
    ("cat < .env", "stdin redirect"),
    ("cat ~/.aws/credentials", "aws credentials"),
    ("cat ~/.aws/credentials.bak", "backup copy of credentials"),
    ("cat ~/.ssh/id_ed25519", "private key"),
    ("cat ~/.netrc", "netrc"),
    ("less +F .env", "less with option"),
    ("tail -n +1 .env .env.local", "two files"),
    ("nl .env", "nl prints the file"),
    ("sort .env | uniq", "sort prints values"),
    ("diff .env .env.bak", "diff prints values"),
    ("awk -F= '{print $2}' .env", "awk prints values"),
    ("jq . credentials.json", "jq on credentials"),
    ("grep TOKEN .env", "grep prints the matching line"),
    ("grep -i secret .env.local", "grep -i"),
    ("grep -n TOKEN .env", "grep -n"),
    ("grep -e TOKEN .env", "grep -e"),
    ("rg TOKEN .env", "ripgrep"),
    # --- S8: pipelines and redirects that still reach the transcript ---
    ("cat .env | base64", "first stage prints"),
    ("cat .env | head -c 100", "head is not names-only"),
    ("cat .env | cut -d= -f2", "values via cut -f2"),
    ("export TOKEN=$(grep TOKEN .env | cut -d= -f2)", "values via cut -f2 in a substitution"),
    ("cat .env >&2", "stderr reaches the transcript"),
    ("cat .env 2>&1", "stderr dup"),
    ("cat .env > /dev/stdout", "terminal device is not a file"),
    ("cat .env > /dev/tty", "terminal device is not a file"),
    ("cat .env >/dev/fd/2", "fd/2"),
    ("cat .env | tee /dev/stderr > /dev/null", "tee to stderr"),
    ("cat .env; echo done", "then something else"),
    ("true && cat .env", "after &&"),
    ("nohup cat .env &", "background"),
    # --- S8: prefixes, carriers and substitutions ---
    ("sudo cat /etc/app/.env", "sudo"),
    ("sudo -u app cat /srv/app/.env", "sudo -u"),
    ("timeout 5 cat .env", "timeout prefix"),
    ("docker exec app cat .env", "reader inside docker exec"),
    ("docker compose exec app cat /app/.env", "compose exec"),
    ("kubectl exec pod -- cat .env", "kubectl exec"),
    ("ssh host cat .env", "ssh unquoted"),
    ("ssh host 'cat .env'", "ssh quoted command"),
    ("ssh host \"bash -c 'cat .env'\"", "carrier depth 2"),
    ("bash -c 'cat .env'", "bash -c"),
    ('sh -c "cat .env"', "sh -c"),
    ("eval 'cat .env'", "eval"),
    ("docker exec app sh -c 'cat .env'", "carrier inside docker exec"),
    ("echo $(cat .env)", "command substitution"),
    ('echo "$(cat .env)"', "quoted command substitution"),
    ("VAR=$(cat .env); echo $VAR", "assignment from substitution"),
    ("printf '%s' \"$(cat .env)\"", "printf lead, substitution reads"),
    ("diff <(cat .env) <(cat .env.bak)", "process substitution reads"),
    # --- S8: script readers ---
    ("python3 -c \"print(open('.env').read())\"", "python open"),
    ("node -e \"console.log(require('fs').readFileSync('.env','utf8'))\"", "node readFileSync"),
    ("ruby -e \"puts File.read('.env')\"", "ruby File.read"),
    # --- S2: ~/.claude.json ---
    ("cat ~/.claude.json", "raw config"),
    ("diff ~/.claude.json ~/.claude.json.bak", "diff prints tokens"),
    ("jq . ~/.claude.json", "whole file"),
    ("jq '.mcpServers.foo.headers' ~/.claude.json", "token field"),
    ("python3 -c 'import json; print(json.load(open(\"/srv/x/.claude.json\")))'", "script read"),
    # --- S1, S3, S4, S5, S6, S7 ---
    ("claude mcp list", "S1"),
    ("cat /proc/1/environ | tr '\\0' '\\n'", "S3"),
    ("docker inspect app", "S4 whole block"),
    ("docker inspect --format '{{.Config.Env}}' app", "S4 env"),
    ("set", "bare set dumps the environment"),
    ("export -p", "export -p"),
    ("env | grep -i token", "S5 via grep"),
    ("printenv GITHUB_TOKEN", "secret value"),
    ("docker compose exec app env", "container env dump"),
    ("ssh host env", "remote env dump"),
    ("npm run env", "accepted false positive: a script literally named env"),
    ("sed 's/token=.*/token=REDACTED/' config.yml", "S6 without -n"),
    ("cat config.yml | grep -v TOKEN", "S7"),
    ("grep -v -i secret_key settings.py", "S7 (arguably searching code)"),
    # --- P1, P2 ---
    ("pytest -q 2>&1 | tail -20 && git commit -m 'fix'", "P1"),
    ("pytest -q | tee out.log; git push", "P1 tee"),
    ("gh run watch 123 | tail -3", "P2"),
    # --- K1 ---
    ("pkill -f node", "K1"),
    ("pkill -f 'node server.js'", "K1 two words"),
]

ALLOW = [
    # --- secret files: safe shapes ---
    ("cat .env.example", "template"),
    ("cat .env.example .env.sample", "templates"),
    ("cat .env.example | cut -d= -f1", "template"),
    ("cat .env.ts", "code file"),
    ("cat .env.d.ts", "typed env module"),
    ("cat src/config/.env.schema.ts", "nested suffix, still a .ts file"),
    ("cat environment.md", "not .env"),
    ("cat README.md", "doc"),
    ("head README.md", "doc"),
    ("tail -n 20 app.log", "log"),
    ("cut -d= -f1 .env", "names only"),
    ("grep -c '^DATABASE_URL=' .env", "presence check"),
    ("grep -v '^#' .env | cut -d= -f1", "names-only pipeline"),
    ("grep -v '^#' .env | cut -d= -f1 | sort", "names-only, three stages"),
    ("sort .env | cut -d= -f1", "names-only pipeline"),
    ("cat .env | cut -d= -f1 | sort", "names-only pipeline"),
    ("cat .env | grep -c TOKEN", "count only"),
    ("cat .env | grep -c .", "count only"),
    ("cat .env | wc -l", "count only"),
    ("cat .env | wc -c", "count bytes"),
    ("diff <(cut -d= -f1 .env) <(cut -d= -f1 .env.example)", "names-only substitutions"),
    ("wc -l .env", "wc"),
    ("ls -la .env", "listing"),
    ("stat .env", "stat"),
    ("test -f .env && echo present", "presence"),
    ("test -s .env && echo nonempty", "presence"),
    ("[ -f .env ] && cat .env.example", "test then template"),
    ("find . -name '.env*'", "find"),
    ("cp .env .env.bak", "copy, nothing printed"),
    ("mv .env .env.old", "move"),
    ("cat .env > backup.env", "stdout to a file"),
    ("cat .env > /tmp/x && wc -l /tmp/x", "to file, then count"),
    ("cat > .env <<'EOF'\nFOO=bar\nEOF", "writing .env via heredoc"),
    ("tee .env <<'EOF'\nFOO=bar\nEOF", "writing .env via tee"),
    ("tee -a .env <<<'X=1'", "tee append"),
    ('echo "TOKEN=abc" > .env', "write"),
    ("sed -i 's/foo/bar/' README.md", "ordinary sed -i"),
    ("cat ~/.ssh/id_ed25519.pub", "public key"),
    ("ls ~/.ssh/ && cat ~/.ssh/config", "ssh config is not a key"),
    ("head -20 ~/.ssh/known_hosts", "known_hosts"),
    ("python3 -c \"from dotenv import load_dotenv; load_dotenv('.env')\"", "load_dotenv doesn't print"),
    ("python3 -c 'import json; print(len(json.load(open(\"package.json\"))))'", "other json"),
    # --- text about commands ---
    ("echo cat .env", "lead echo"),
    ('echo "cat .env"', "quoted text"),
    ("echo 'run: cat .env' >> notes.md", "text that mentions the command"),
    ("git commit -m 'docs: explain why cat .env is blocked'", "commit message"),
    ('git commit -m "feat: parse .env with cat-like reader"', "commit message"),
    ("git commit -m 'fix tsc | pipes'", "pipe inside a commit message is not a pipeline"),
    ("git add .env.example && git commit -m 'add template'", "template add"),
    ("python3 - <<'EOF'\nprint('cat .env is dangerous')\nEOF", "heredoc body ignored"),
    # --- carriers with harmless commands ---
    ("ssh host 'uptime'", "ssh"),
    ("ssh host 'uptime; df -h'", "ssh"),
    ("ssh host 'cat /etc/os-release'", "ssh cat of a non-secret"),
    ("bash -c 'ls -la .env'", "carrier harmless"),
    ("docker exec app sh -c 'ls /app/.env'", "carrier harmless"),
    # --- S2 safe shapes ---
    ("jq '.mcpServers | keys' ~/.claude.json", "safe jq"),
    ("grep -c mcpServers ~/.claude.json", "count only"),
    ("cp ~/.claude.json ~/.claude.json.bak", "copy"),
    ("claude mcp add foo -- npx foo", "mcp add"),
    # --- S3, S4, S5 safe shapes ---
    ("tr '\\0' '\\n' < /proc/1/environ | grep -oE '^[A-Z_][A-Z0-9_]*='", "environ names"),
    ("cat /proc/cpuinfo", "not environ"),
    ("docker inspect --format '{{.State.Status}}' app", "one field"),
    ("docker inspect --format '{{json .Config.Env}}' app | jq -r '.[]' | cut -d= -f1", "env names"),
    ("env | cut -d= -f1 | sort", "names only"),
    ("env FOO=bar ./run.sh", "env as launcher"),
    ("docker compose exec app env | cut -d= -f1", "names only in container"),
    ("set -e; set -o pipefail; npm test", "set with arguments"),
    ("export FOO=bar", "export assignment"),
    ("printenv CLAUDE_CODE_SESSION_ID", "session id is not a secret"),
    ("printenv HOME", "harmless variable"),
    # --- S6, S7 safe shapes ---
    ("sed -n 's/token=.*/token=REDACTED/p' config.yml", "fail-closed redaction"),
    ("grep -v '^#' README.md", "grep -v on a non-secret word"),
    # --- P1, P2, K1 safe shapes ---
    ("pytest -q && git push", "no pipe"),
    ("set -o pipefail; pytest -q | tail -20 && git push", "pipefail"),
    ("pytest -q | tail -20", "no ship step"),
    ("npm test -- --watch=false | cat; echo done", "no ship step"),
    ("gh run watch 123 --exit-status", "unpiped"),
    ("gh run watch 123 --exit-status || echo failed", "unpiped with ||"),
    ("pkill -f 'vite --port 5173'", "specific (port)"),
    ("pkill -f /srv/app/worker.py", "specific (path)"),
    ("kill 12345", "pid"),
]


def decision(cmd):
    res = bash_guard.decide(cmd)
    return "allow" if res is None else res[0]


class Battery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for var in ("RELAY_GUARD_OFF", "RELAY_GUARD_MODE"):
            os.environ.pop(var, None)

    def test_no_duplicate_rows(self):
        cmds = [c for c, _ in DENY + ALLOW]
        self.assertEqual(len(cmds), len(set(cmds)), "a command appears twice in the battery")

    def test_deny(self):
        for cmd, note in DENY:
            with self.subTest(cmd=cmd, note=note):
                self.assertEqual(decision(cmd), "deny", f"should deny: {cmd}  ({note})")

    def test_allow(self):
        for cmd, note in ALLOW:
            with self.subTest(cmd=cmd, note=note):
                self.assertEqual(decision(cmd), "allow", f"should allow: {cmd}  ({note})")

    def test_adversarial_input_is_fast(self):
        big = ("cat .env " + "| grep x " * 300) + "\n" + ("echo 'a' ; " * 400) + "'" * 2000 \
              + "$(" * 50 + "cat .env" + ")" * 50
        for cmd in (big, "cat .env" + " |" * 2000):
            t0 = time.time()
            decision(cmd)
            self.assertLess(time.time() - t0, 2.0, "guard must stay far below the 10s hook timeout")


if __name__ == "__main__":
    unittest.main()
