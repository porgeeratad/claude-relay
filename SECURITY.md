# Security

Relay runs a hook (`hooks/bash_guard.py`) on every Bash call Claude Code makes, and its skills write handoff and
thread files on your machine. Anything that lets the hook leak data, execute something it shouldn't, block work
when it should fail open, or lets a skill write secrets into a file or commit, is a security issue.

Please report it privately: **GitHub → Security → Report a vulnerability** on this repository. Do not open a public
issue. You will get an answer within a week.

Design constraints we hold ourselves to:

- The hook is Python stdlib only, makes no network calls, reads no files, and fails open (`|| true`).
- The guard is a seatbelt, not a sandbox: it catches common accidents, not a determined attacker. Use Claude Code's
  permission rules and sandboxing for hard boundaries.
- Handoffs and threads default to a directory outside your repository.

In scope: `hooks/`, `scripts/`, `skills/`, `.githooks/`. Out of scope: Claude Code itself (report to Anthropic).
