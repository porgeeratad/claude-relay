# Contributing

Thanks for wanting to help. Bug reports, new guard cases, ideas and pull requests are all welcome.

## Run it from source

```sh
claude --plugin-dir .                       # a session with your working copy of the plugin loaded
git config core.hooksPath .githooks         # once per clone: leak-check runs before every commit
```

## Where things are

| Path | What |
|---|---|
| `skills/<name>/SKILL.md` | the four skills; plain Markdown instructions Claude follows |
| `skills/pair/templates/` | thread and design-doc templates for `/relay:pair` |
| `docs/HANDOFF-FORMAT.md` | the handoff file contract shared by `/relay:handoff` and `/relay:pickup` |
| `scripts/relay_dir.py` | the one place that decides where handoffs, threads and markers live |
| `hooks/bash_guard.py`, `hooks/hooks.json` | the PreToolUse guard and its registration |
| `scripts/leak-check.sh`, `.githooks/pre-commit` | keeps private paths, IPs, ids and credentials out of this public repo |
| `tests/` | unit tests, the review battery, the leak-check self-test |

## Rules for the guard

- Python standard library only, no network, no file reads, and fail open: an exception means no decision.
- Every rule change comes with at least one deny case and one allow case. False positives are bugs too.
- Suggest the safe alternative in the message. A block without a way forward just teaches people to disable the hook.
- Keep it fast: the battery includes a timing test.

## Rules for the skills

- Skills never guess paths: they ask `scripts/relay_dir.py`.
- Keep the receipt honest. Nothing may print CLEAN when a step failed.
- Write examples with a made-up project (`acme-api`), never with real handoffs.

## Checks before a pull request

```sh
python3 tests/test_bash_guard.py && python3 tests/test_bash_guard_battery.py && python3 tests/test_relay_dir.py
scripts/leak-check.sh all && bash tests/test_leak_check.sh
claude plugin validate --strict .claude-plugin/plugin.json
```

CI runs the same on Linux and macOS (including macOS's bash 3.2).
