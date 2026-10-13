# Handoff format (relay format 1)

A handoff is the one file a future session reads to continue your work: what
happened, what is left, and the exact command that picks it up.
`/relay:handoff` writes it, `/relay:pickup` reads it. Both follow this spec, so
the **file is the contract** — not the chat transcript, not the user's memory.

## 1. Where files live

Skills never guess paths. They ask the plugin's resolver:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" handoffs   # handoff files
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" threads    # /relay:pair threads
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" state      # per-session markers
```

Each call prints one absolute directory (created if missing).

Base directory, first match wins:

1. `$RELAY_DIR` (environment)
2. `"dir"` in `.claude/relay.json` at the toplevel of the current checkout
   (`git rev-parse --show-toplevel`) — a relative value is resolved from that
   toplevel, so in-repo handoffs follow the checkout: each worktree gets its own
3. `${XDG_STATE_HOME:-~/.local/state}/claude-relay/<slug>/` — the default.
   It lives **outside the repository**, so a handoff can never end up in a
   commit, a PR, or a public repo by accident. With this default every
   worktree of one repository shares one directory. Teams that want handoffs
   shared through git opt in with `"dir": "docs/handoffs"`.

Definitions:

- **Project root** = parent of `git rev-parse --git-common-dir` (the main
  worktree). It is what the default location's slug is built from. Outside
  git the project root is the current directory.
- **Slug** = the project root path with every character outside `[A-Za-z0-9]`
  replaced by `-`. Example: `/srv/work/acme-api` → `-srv-work-acme-api`.
- **Session id** = `printenv CLAUDE_CODE_SESSION_ID` (set in every Bash call
  of a Claude Code session).

Layout under the base directory:

```
handoffs/HANDOFF-YYYY-MM-DD-<topic>.md    # this spec
threads/YYYY-MM-DD-<topic>.md             # /relay:pair transport
state/<session-id>.json                   # delta-mode marker, one per session
```

`.claude/relay.json` keys:

| key          | values                                                                  | default               |
|--------------|-------------------------------------------------------------------------|-----------------------|
| `dir`        | base directory, absolute or relative to the project root                | XDG default above     |
| `push`       | `ask` · `auto` · `never` — may `/relay:handoff` push work repositories  | `ask`                 |
| `design_dir` | where `/relay:pair` keeps design docs + Decision Log (inside the repo)  | `docs/design`         |

## 2. File name

`HANDOFF-YYYY-MM-DD-<topic>.md`

- date = local date of the close
- `<topic>` = kebab-case, at most four words, what the session was about
  (`rate-limiter-rollout`, not `session` or `misc`)
- one file per session. A second `/relay:handoff` in the same session
  **appends** (§6) — it never creates a second file.

## 3. Frontmatter

```yaml
---
title: "Handoff: acme-api — rate limiter rollout — 2026-10-13"
project: acme-api          # basename of the project root
date: 2026-10-13
session: <session-id>      # printenv CLAUDE_CODE_SESSION_ID of the writing session
status: current            # current | superseded
format: 1                  # version of this spec
---
```

- `session` feeds the `claude --resume` line of the NEXT-CMD block.
- `status`: a project has **at most one `current` handoff**. Creating a new
  handoff flips the previous `current` file to `superseded` (frontmatter edit
  only — bodies are never rewritten). `/relay:pickup` with no argument opens
  the `current` file; if none is marked current it opens the newest file by
  date and says so.

## 4. Required sections, in this order

| section           | content                                                                                                                   |
|-------------------|---------------------------------------------------------------------------------------------------------------------------|
| `## Context`      | 1–3 lines: what this session set out to do and why.                                                                       |
| `## Status`       | bullets: every touched repository as `path @ sha — pushed ✅ / unpushed ❌`, deploy or runtime state, anything still running. |
| `## Changes`      | table `Commit/Action \| Description`, one row per commit or notable non-commit action (config change, deploy, migration). |
| `## Pending`      | checkbox list, see §5.                                                                                                     |
| `## Gotchas`      | what went wrong and how you got past it, so the next session does not repeat it. `none` is a valid body.                 |
| `## Next session` | exactly one NEXT-CMD block (§5) inside a fenced code block.                                                                |

A file with a missing or renamed section is invalid: `/relay:pickup` warns and
falls back to reading the whole file instead of the sections it expects.

## 5. Pending list and NEXT-CMD block

Pending:

```markdown
- [ ] <action, self-contained> — <blocker or who decides, if any>
- [ ] run the migration on staging — waiting on: user (needs the staging window)
- [x] <finished items stay, ticked, until the file is superseded>
```

- Every item must make sense **without the chat transcript**: name the file,
  the command, or the decision.
- Order is priority. `/relay:pickup` starts at the first unticked item.
- Items that need the user carry `waiting on: user` so pickup can list them
  first and ask once.

NEXT-CMD block. The same text is the last block of the receipt that
`/relay:handoff` prints, so the user can copy it from the terminal or from the
file — both work.

```
── NEXT-CMD ──
/relay:pickup
<first thing to do>
<what to watch out for>
<what you are waiting on from the user>
(resume this session instead: cd <project root> && claude --resume <session-id>)
──────────────
```

- Brief ≤ 5 lines; drop a placeholder line if it would be empty.
- `/relay:pickup` alone opens the `current` handoff of the project in the
  current directory; `/relay:pickup HANDOFF-2026-10-13-rate-limiter-rollout.md`
  targets one file.
- The `claude --resume` line is the only place an absolute path is expected.

## 6. Delta updates — second `/relay:handoff` in the same session

The state marker (§7) tells the skill this session already closed once. Then:

1. Never create a new HANDOFF file.
2. Append `## Update HH:MM` (local time) at the end of the file: what happened
   after `closed_at` — new commits (`git log <sha>..HEAD` per repo in the
   marker), decisions taken, new blockers.
3. Edit `## Pending` in place: tick finished items, append new ones at the end.
4. Replace the NEXT-CMD block inside `## Next session` with a fresh one. This
   is the only section whose content is overwritten.
5. Update the marker: `count` + 1, new `closed_at`, new `repos` shas.

The receipt for a delta close is headed `DELTA #<count>`.

## 7. State marker

`state/<session-id>.json`, written after every successful close:

```json
{
  "closed_at": "2026-10-13T18:40:00+00:00",
  "count": 1,
  "handoff": "/srv/work/.local/state/claude-relay/-srv-work-acme-api/handoffs/HANDOFF-2026-10-13-rate-limiter-rollout.md",
  "repos": {
    "/srv/work/acme-api": "9b1f2c3"
  }
}
```

| field       | meaning                                                                                   |
|-------------|-------------------------------------------------------------------------------------------|
| `closed_at` | ISO 8601 with UTC offset. Delta mode reports only what happened after this instant.       |
| `count`     | number of closes in this session; `1` = first close, the receipt prints `DELTA #n` for n ≥ 2 |
| `handoff`   | absolute path of the handoff this session owns                                            |
| `repos`     | repository root → HEAD sha at close time; the delta diff is `git log <sha>..HEAD`          |

Markers are keyed by session id, so parallel sessions on the same project do
not clobber each other. A stale marker is harmless — `state/` can be deleted at
any time; the next close simply starts at `count: 1` again.

## 8. Content rules

- No secrets, tokens, or raw payloads — ever. Reference a file path and a
  PASS/FAIL instead. The handoff directory is private by default, but that is
  not a reason to put credentials in it.
- Paths relative to the project root, except the `claude --resume` line.
- Keep it under ~150 lines. Details belong in the repository (docs, commit
  messages), not in the handoff.
- Receipt honesty: if a step failed (push rejected, tests red, deploy skipped)
  both the handoff and the receipt show ❌ with what the user must do. A
  receipt never says CLEAN while a ❌ is present. A step the user skipped on
  purpose (`--no-push`, `push: never`) shows ⏸ with the reason; ⏸ alone does
  not block CLEAN. A push the user deferred when asked ("later") is ❌.
- Language is the user's choice; headings and frontmatter keys are fixed.

## 9. Full example

Project root `/srv/work/acme-api` (the example user's home is `/srv/work`),
no `.claude/relay.json`, so the file is
`/srv/work/.local/state/claude-relay/-srv-work-acme-api/handoffs/HANDOFF-2026-10-13-rate-limiter-rollout.md`:

```markdown
---
title: "Handoff: acme-api — rate limiter rollout — 2026-10-13"
project: acme-api
date: 2026-10-13
session: <session-id>
status: current
format: 1
---

# Handoff: acme-api — rate limiter rollout — 2026-10-13

## Context
Ship the token-bucket rate limiter behind a feature flag so it can go to
staging before the Thursday release. Replaces the per-route counters that
double-count retries.

## Status
- `/srv/work/acme-api` @ `9b1f2c3` — pushed ✅ (main, CI green)
- staging: flag `RATE_LIMIT_V2=off`, limiter deployed but inactive
- no background jobs left running

## Changes
| Commit/Action | Description |
|---|---|
| `4e7d0a1` | `internal/ratelimit`: token bucket with per-client keys, 42 unit tests |
| `9b1f2c3` | middleware wired behind `RATE_LIMIT_V2`, old counters kept for rollback |
| deploy | staging rollout via `make deploy-staging`, flag off |

## Pending
- [ ] enable `RATE_LIMIT_V2=on` on staging and watch `ratelimit_rejected_total` for 30 min — waiting on: user (staging window)
- [ ] delete the legacy counters in `internal/middleware/counters.go` once staging is clean
- [ ] decide the default burst size (currently 20; product asked about 50) — waiting on: user
- [x] unit tests for bucket refill edge cases

## Gotchas
- `make deploy-staging` silently skips the config map when `kubectl` context is
  not `staging`; check `kubectl config current-context` first.
- Retried requests carry `X-Retry: 1`; the limiter must count them once —
  covered by `TestRetryNotDoubleCounted`.

## Next session
```
── NEXT-CMD ──
/relay:pickup
first: flip RATE_LIMIT_V2=on on staging, watch ratelimit_rejected_total 30 min
watch: kubectl context must be staging before make deploy-staging
waiting on user: staging window · default burst size (20 vs 50)
(resume this session instead: cd /srv/work/acme-api && claude --resume <session-id>)
──────────────
```
```

After a delta close at 21:05 the same file gains, at the end:

```markdown
## Update 21:05
- `c0ffee1` legacy counters removed (staging clean for 45 min, 0 false rejects)
- burst size stays 20 — user decided, see Decision Log in docs/design/rate-limiter.md
```

with the Pending items ticked in place and a new NEXT-CMD block replacing the
old one under `## Next session`.
