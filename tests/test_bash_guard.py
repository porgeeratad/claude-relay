#!/usr/bin/env python3
"""Tests for hooks/bash_guard.py — run: python3 tests/test_bash_guard.py

All fixtures are synthetic. Each case runs the hook as Claude Code would:
JSON on stdin, decision JSON (or nothing) on stdout.
"""
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "bash_guard.py")

DENY = [
    ("S1", "claude mcp list"),
    ("S1", "claude mcp get acme-docs"),
    ("S2", "cat ~/.claude.json"),
    ("S2", "grep -A3 acme ~/.claude.json"),
    ("S2", "jq '.mcpServers' ~/.claude.json"),
    ("S2", "python3 -c \"import json; print(json.load(open('/srv/u/.claude.json')))\""),
    ("S2", "python3 - <<'EOF'\nimport json\nprint(json.load(open('/srv/u/.claude.json')))\nEOF"),
    ("S3", "cat /proc/1234/environ"),
    ("S3", "tr '\\0' '\\n' < /proc/1/environ | cut -d= -f1-2"),
    ("S4", "docker inspect acme-api"),
    ("S4", "docker inspect --format '{{.Config.Env}}' acme-api"),
    ("S5", "env"),
    ("S5", "printenv | sort"),
    ("S5", "docker exec acme-api env"),
    ("S5", "ssh build-box 'env'"),
    ("S5", "printenv ACME_API_TOKEN"),
    ("S6", "sed 's/token=.*/token=REDACTED/' config.ini"),
    ("S7", "grep -v API_KEY .env.production.local"),
    ("S8", "cat .env"),
    ("S8", "head -5 .env.production"),
    ("S8", "tail ~/.netrc"),
    ("S8", "cat ~/.ssh/id_ed25519"),
    ("P1", "pytest -q | tail -3 && git push"),
    ("P1", "npm test | grep -v warn; git commit -am wip"),
    ("P1", "cargo test 2>&1 | tail -20 && npm publish"),
    ("P2", "gh run watch 123456 | tail -5"),
    ("K1", "pkill -f node"),
    ("K1", "pkill -9 -f 'python server'"),
]

ALLOW = [
    "git status",
    "ls -la",
    "jq '.mcpServers | keys' ~/.claude.json",
    "jq '.mcpServers[].command' ~/.claude.json",
    "grep -c acme ~/.claude.json",
    "sed -i 's/\\.claude\\.json/settings.json/' docs/setup.md",
    "tr '\\0' '\\n' < /proc/1/environ | grep -oE '^[A-Z_][A-Z0-9_]*='",
    "docker inspect --format '{{.State.Status}}' acme-api",
    "env | cut -d= -f1",
    "env FOO=1 make build",
    "set -euo pipefail; make test",
    "[ -n \"${ACME_API_TOKEN-}\" ] && echo set",
    "sed -n 's/token=.*/token=REDACTED/p' config.ini",
    "grep -v '^#' requirements.txt",
    "cut -d= -f1 .env",
    "cat .env.example",
    "cat > .env <<'EOF'\nACME_URL=http://localhost\nEOF",
    "cat ~/.ssh/id_ed25519.pub",
    "pytest -q && git push",
    "set -o pipefail; pytest -q | tail -3 && git push",
    "pytest -q | tail -3",
    "gh run watch 123456 --exit-status",
    "pkill -f 'node server.js --port 3000'",
    "pkill -f /opt/acme/bin/worker",
    "kill 4242",
    "cat > notes.md <<'EOF'\nnever run `env` or `cat .env` here\nEOF",
]


def run_hook(payload, env=None):
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("RELAY_GUARD")}
    full_env.update(env or {})
    res = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, env=full_env)
    return res.returncode, res.stdout.strip()


def bash(cmd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


class BashGuardTest(unittest.TestCase):
    def test_deny_cases(self):
        for rid, cmd in DENY:
            with self.subTest(cmd=cmd):
                code, out = run_hook(bash(cmd))
                self.assertEqual(code, 0)
                self.assertTrue(out, f"expected {rid} to fire")
                dec = json.loads(out)["hookSpecificOutput"]
                self.assertEqual(dec["permissionDecision"], "deny")
                self.assertIn(f"[relay guard {rid}]", dec["permissionDecisionReason"])

    def test_allow_cases(self):
        for cmd in ALLOW:
            with self.subTest(cmd=cmd):
                code, out = run_hook(bash(cmd))
                self.assertEqual((code, out), (0, ""), f"false positive: {out}")

    def test_rule_can_be_disabled(self):
        self.assertEqual(run_hook(bash("pkill -f node"), {"RELAY_GUARD_OFF": "K1"}), (0, ""))
        self.assertEqual(run_hook(bash("cat .env"), {"RELAY_GUARD_OFF": "all"}), (0, ""))
        _, out = run_hook(bash("cat .env"), {"RELAY_GUARD_OFF": "K1"})
        self.assertIn("S8", out)

    def test_ask_mode(self):
        _, out = run_hook(bash("cat .env"), {"RELAY_GUARD_MODE": "ask"})
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_fail_open(self):
        self.assertEqual(run_hook("not json"), (0, ""))
        self.assertEqual(run_hook(json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}})), (0, ""))
        self.assertEqual(run_hook(json.dumps({"tool_name": "Bash"})), (0, ""))

    def test_every_rule_has_a_case(self):
        sys.path.insert(0, os.path.dirname(HOOK))
        import bash_guard
        self.assertEqual({rid for rid, _ in DENY}, set(bash_guard.RULES))


if __name__ == "__main__":
    unittest.main(verbosity=1)
