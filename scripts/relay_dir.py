#!/usr/bin/env python3
"""Resolve (and create) the relay directory for the current project.

Usage:
    relay_dir.py                 # base dir
    relay_dir.py handoffs        # <base>/handoffs
    relay_dir.py threads         # <base>/threads
    relay_dir.py state           # <base>/state
    relay_dir.py --config        # print the effective config as JSON

Resolution order for the base dir:
    1. $RELAY_DIR (absolute, or relative to the git toplevel)
    2. "dir" in <git toplevel>/.claude/relay.json (absolute, or relative to the toplevel)
    3. ${XDG_STATE_HOME:-~/.local/state}/claude-relay/<slug>

<slug> is the project root with every character outside [A-Za-z0-9] replaced by "-".
The project root is the main worktree (parent of `git rev-parse --git-common-dir`),
so every worktree of one repository shares the same default directory.
Outside git, the project root is the current directory.

Stdlib only. Prints one absolute path on stdout. Exit 2 on bad usage or bad config.
"""
import json
import os
import re
import subprocess
import sys

SUBDIRS = ("handoffs", "threads", "state")
DEFAULTS = {"dir": None, "push": "ask", "design_dir": "docs/design"}
PUSH_VALUES = ("ask", "auto", "never")


def git(*args, cwd=None):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def toplevel(cwd):
    top = git("rev-parse", "--show-toplevel", cwd=cwd)
    return os.path.realpath(top) if top else None


def project_root(cwd):
    common = git("rev-parse", "--git-common-dir", cwd=cwd)
    if not common:
        return os.path.realpath(cwd)
    if not os.path.isabs(common):
        common = os.path.join(cwd, common)
    common = os.path.realpath(common)
    # A normal repository keeps its common dir at <root>/.git; a bare one is the repo itself.
    return os.path.dirname(common) if os.path.basename(common) == ".git" else common


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def load_config(top):
    cfg = dict(DEFAULTS)
    if not top:
        return cfg
    path = os.path.join(top, ".claude", "relay.json")
    if not os.path.isfile(path):
        return cfg
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"relay_dir: cannot read {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"relay_dir: {path} must hold a JSON object")
    for key in DEFAULTS:
        if key in data:
            cfg[key] = data[key]
    if cfg["push"] not in PUSH_VALUES:
        raise SystemExit(f"relay_dir: {path}: push must be one of {', '.join(PUSH_VALUES)}")
    for key in ("dir", "design_dir"):
        if cfg[key] is not None and not isinstance(cfg[key], str):
            raise SystemExit(f"relay_dir: {path}: {key} must be a string")
    return cfg


def base_dir(cwd):
    top = toplevel(cwd)
    anchor = top or os.path.realpath(cwd)
    cfg = load_config(top)
    chosen = os.environ.get("RELAY_DIR") or cfg["dir"]
    if chosen:
        chosen = os.path.expanduser(chosen)
        return os.path.realpath(chosen if os.path.isabs(chosen) else os.path.join(anchor, chosen)), cfg
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(state, "claude-relay", slug(project_root(cwd))), cfg


def main(argv):
    if len(argv) > 1 or (argv and argv[0] not in SUBDIRS + ("--config", "-h", "--help")):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    cwd = os.getcwd()
    try:
        base, cfg = base_dir(cwd)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    if argv and argv[0] == "--config":
        print(json.dumps({**cfg, "base": base, "project_root": project_root(cwd)}, indent=2))
        return 0
    path = os.path.join(base, argv[0]) if argv else base
    os.makedirs(path, exist_ok=True)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
