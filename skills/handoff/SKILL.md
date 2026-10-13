---
name: handoff
description: Close a work session cleanly. Sweeps unfinished work, commits (and pushes per policy), writes a handoff file the next session can pick up, then prints an honest receipt and a ready-to-paste NEXT-CMD block. Use when the user says "/relay:handoff", "wrap up", "close the session", "write a handoff", "save progress for tomorrow", "I'm done for today", or asks for the command to resume later. Running it again in the same session appends a delta instead of creating a new file.
argument-hint: "[topic] [--stay] [--no-push]"
---

# /relay:handoff — close a session so the next one starts in seconds

The order is fixed: don't skip steps or reorder them. Read every file before you edit it.

File format, naming and the state marker are defined in `${CLAUDE_PLUGIN_ROOT}/docs/HANDOFF-FORMAT.md`. Read it the first time you run this skill in a session.

| Flag | Effect |
|---|---|
| `[topic]` | kebab-case topic for the file name (default: derive one from the main work of the session) |
| `--stay` | checkpoint: do everything, but the session keeps going (receipt header says CHECKPOINT) |
| `--no-push` | commit but never push, whatever the policy says |

## 0. Preflight

```bash
printenv CLAUDE_CODE_SESSION_ID                                   # session id
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" handoffs      # where handoffs live
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" state         # where markers live
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" --config      # push policy, design_dir
```

Use the printed paths as they are. Never guess a path.

- If `<state>/<session-id>.json` exists, this session already ran a handoff: switch to **Delta mode** (below) and don't create a second file.
- If `CLAUDE_CODE_SESSION_ID` is empty, write `session: unknown` in the frontmatter, skip delta detection, **don't write a marker** (step 5), and add `Delta mode: unavailable (no session id)` to the receipt. A shared `unknown` marker would send the next session's delta into someone else's handoff.

## 1. Sweep (before writing anything)

- For each repository touched in this session, run `git status -sb` and check `git log @{u}.. --oneline 2>/dev/null` to find uncommitted or unpushed work.
- Background jobs, dev servers and watchers you started: decide for each one whether to keep it or stop it. List the survivors with the reason.
- Things discussed but not done: write each one as an actionable Pending item (verb + object + where).
- Tell the user one line: `N pending items will go into the handoff`.

## 2. Commit, then push per policy

- Stage only the files you changed in this session: `git add <paths>`. Never `git add -A` or `git add .`, because other sessions or people may have work in the tree.
- Commit on the current branch. Don't create or switch branches unless the user or the repository's written rules ask for it. Follow the repository's commit style and the user's instructions; they win over this skill.
- A failing pre-commit hook means fix the problem or report it. Never pass `--no-verify`.
- Push policy comes from `push` in the config: `auto` pushes, `ask` (the default) asks once for all repos together, and `never` skips the push. `--no-push` overrides all three.
- Report a repo as **pushed** only when `git status -sb` afterwards shows it level with its upstream.

## 3. Write the handoff file

- Path: `<handoffs>/HANDOFF-YYYY-MM-DD-<topic>.md`. Use the local date.
- If that file exists, Read it. When its `session:` is this session, update it. When it belongs to another session, don't touch it: name yours `<topic>-2` (`-3`, …) instead.
- If an older handoff of this project has `status: current` and this one replaces it, set the old one to `superseded`.
- Frontmatter and the required sections, in order, come from the spec: `## Context` · `## Status` · `## Changes` · `## Pending` · `## Gotchas` · `## Next session`.
- Pending items read on their own without the chat. Order means priority, and items the user must decide end with `— waiting on: user`.
- Paths are relative to the project root. The only exception is the `claude --resume` line.
- `## Gotchas` = what cost time in this session, written so the next session doesn't pay twice.
- `## Next session` = the NEXT-CMD block from step 4, word for word.
- Never put secrets, tokens or credential values in a handoff. Name where they live instead.

If the project keeps a CHANGELOG and code changed, append one entry, but only when the project already uses that convention.

## 4. Receipt + NEXT-CMD (always print this, in every mode)

```
── HANDOFF RECEIPT ──                  (--stay: "── HANDOFF CHECKPOINT ──" · delta: "── HANDOFF RECEIPT · DELTA #n ──")
Repos      : acme-api@3f2c1ab pushed ✅ | acme-web 2 files uncommitted ❌ (tests red, left for next session)
Handoff    : <path> ✅
Pending    : 4 items → ## Pending
Background : none | dev server on :3000 left running (user is testing)
─────────────────────
CLOSED CLEAN ✅          (or: ⚠️ NOT CLEAN — <each failed row + what the user must do>)

── NEXT-CMD ──
/relay:pickup <topic>
<brief, 5 lines at most: first thing to do · what to watch out for · what is waiting on the user>
(or resume this exact session: cd <cwd> && claude --resume <session-id>)
──────────────
```

- Write `CLOSED CLEAN` only when every row passed. Anything uncommitted, failed, or unpushed without the user choosing it makes it `⚠️ NOT CLEAN`. Never overstate.
- A push skipped **by the user's choice** (`--no-push`, or `push: never`) is reported as `push skipped (by choice) ⏸`. It doesn't by itself make the receipt NOT CLEAN. A push the user deferred when asked ("later") does.
- The receipt answers the question "did yesterday's session close properly?", so it has to be true.

Example of a receipt that is not clean:

```
── HANDOFF RECEIPT ──
Repos      : acme-api@9b1e004 committed, push skipped (policy ask → user said later) ⚠️
Handoff    : <handoffs>/HANDOFF-2026-03-14-rate-limit.md ✅
Pending    : 2 items → ## Pending
Background : none
─────────────────────
⚠️ NOT CLEAN — acme-api has 1 unpushed commit: run `git push` when ready
```

## 5. Marker

Write `<state>/<session-id>.json` with the schema from the spec (`closed_at`, `count`, `handoff`, `repos` → sha). It's what turns a second run into a delta. Skip this step when there's no session id.

## Delta mode (second run in the same session)

Only handle what happened after `closed_at` in the marker:

1. Sweep: new commits per repo (`git log <sha-from-marker>..HEAD --oneline`), plus Pending items that changed.
2. Nothing new at all: don't touch any file. Print a short receipt ("nothing new since the last handoff") and the NEXT-CMD block.
3. Something new: Read the handoff named in the marker. Append `## Update HH:MM` covering what was done, the commits, and Pending changes. Tick the `[x]` items that are now done in the original list. Replace `## Next session` with the new block. **Never create a new handoff file.**
4. Receipt header `DELTA #n`, then update the marker (`count + 1`, `closed_at`, `repos`).

## Never

- `git add -A`, `--no-verify`, force-push.
- Report pushed or clean when it isn't.
- End without the NEXT-CMD block (the user needs it to resume).
- Write secrets into the handoff, the receipt or the commit message.
