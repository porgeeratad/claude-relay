#!/usr/bin/env python3
"""Tests for scripts/relay_dir.py — run: python3 tests/test_relay_dir.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "relay_dir.py")


def run(cwd, *args, env=None):
    full_env = {k: v for k, v in os.environ.items() if k not in ("RELAY_DIR", "XDG_STATE_HOME")}
    full_env.update(env or {})
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=full_env,
                          capture_output=True, text=True)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",  # leak-allow
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})  # leak-allow


class RelayDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.state = os.path.join(self.tmp, "state-home")
        self.repo = os.path.join(self.tmp, "acme-api")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def env(self, **extra):
        return {"XDG_STATE_HOME": self.state, **extra}

    def test_default_uses_xdg_state_and_slug(self):
        res = run(self.repo, "handoffs", env=self.env())
        self.assertEqual(res.returncode, 0, res.stderr)
        slug = "".join(c if c.isalnum() and c.isascii() else "-" for c in self.repo)
        self.assertEqual(res.stdout.strip(), os.path.join(self.state, "claude-relay", slug, "handoffs"))
        self.assertTrue(os.path.isdir(res.stdout.strip()))

    def test_subdirectory_resolves_to_same_project(self):
        sub = os.path.join(self.repo, "src", "deep")
        os.makedirs(sub)
        a = run(self.repo, env=self.env()).stdout.strip()
        b = run(sub, env=self.env()).stdout.strip()
        self.assertEqual(a, b)

    def test_worktrees_share_one_dir(self):
        wt = os.path.join(self.tmp, "acme-api-wt")
        git(self.repo, "worktree", "add", "-q", wt, "-b", "feature")
        a = run(self.repo, "threads", env=self.env()).stdout.strip()
        b = run(wt, "threads", env=self.env()).stdout.strip()
        self.assertEqual(a, b)

    def test_non_git_dir_uses_cwd(self):
        plain = os.path.join(self.tmp, "notes")
        os.makedirs(plain)
        res = run(plain, env=self.env())
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(res.stdout.strip().endswith("-notes"))

    def test_env_override_wins(self):
        target = os.path.join(self.tmp, "custom")
        res = run(self.repo, "state", env=self.env(RELAY_DIR=target))
        self.assertEqual(res.stdout.strip(), os.path.join(target, "state"))

    def test_relay_json_relative_dir(self):
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "relay.json"), "w") as fh:
            json.dump({"dir": "docs/relay", "push": "auto"}, fh)
        res = run(self.repo, "handoffs", env=self.env())
        self.assertEqual(res.stdout.strip(), os.path.join(self.repo, "docs", "relay", "handoffs"))
        cfg = json.loads(run(self.repo, "--config", env=self.env()).stdout)
        self.assertEqual(cfg["push"], "auto")
        self.assertEqual(cfg["design_dir"], "docs/design")

    def test_bad_push_value_is_rejected(self):
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "relay.json"), "w") as fh:
            json.dump({"push": "yes"}, fh)
        res = run(self.repo, env=self.env())
        self.assertEqual(res.returncode, 2)
        self.assertIn("push must be one of", res.stderr)

    def test_broken_json_is_rejected(self):
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "relay.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(run(self.repo, env=self.env()).returncode, 2)

    def test_unknown_argument(self):
        self.assertEqual(run(self.repo, "nope", env=self.env()).returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
