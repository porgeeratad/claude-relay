---
name: pickup
description: Start a session where the last one stopped. Finds the latest handoff for this project, checks the repository against what it claims, and continues from its Pending list. Use when the user says "/relay:pickup", "pick up where we left off", "continue from the handoff", "what was I doing", "resume yesterday's work", or pastes a NEXT-CMD block.
argument-hint: "[topic]"
---

# /relay:pickup — continue from the last handoff

The handoff is a claim, not the truth: read it, then verify it against the repository before acting on it.

## 1. Find the handoff (no guessing)

```bash
H=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" handoffs)
ls "$H"/HANDOFF-*.md 2>/dev/null | sort -r | head -5     # newest date first (the date is in the name)
```

- **Read only paths that `ls` printed.** Never build a file name from memory or from the topic. A guessed path that doesn't exist wastes the turn.
- No argument: open the file marked `status: current` (`grep -l '^status: current' "$H"/HANDOFF-*.md`). If no file is marked current, open the newest one and say so.
- An argument that is a file name (`HANDOFF-….md`) opens that file. Any other argument is a topic: pick the newest file whose name contains it. If nothing matches, show the list and ask one question.
- If the list is empty, say so and print the directory you searched. Mention that `.claude/relay.json` (`dir`) or `RELAY_DIR` can point somewhere else. Then offer a fresh start from `git log --oneline -10` and `git status -sb`.

## 2. Read

- Read the chosen handoff in full.
- Read older handoffs only when the new one points to them.
- If the handoff names a design doc or a pair thread, open it only when the first Pending item needs it.

## 3. Verify against the repository

For each repository the handoff mentions:

```bash
git -C <repo> status -sb
git -C <repo> log --oneline -10
```

Look for drift between the handoff and what you see:

- commits made after the handoff's date (someone kept working)
- a different branch from the one the handoff names
- Pending items that already look done (you can see the commit or the file), marked `✓?`
- uncommitted changes the handoff doesn't mention

## 4. Report, then act

Keep the report short:

```
Picked up: <handoff file> (<date>, session <id>)
Status   : <1–2 lines>
Pending  : 1. … 2. … 3. ✓? (looks done: <evidence>)
Gotchas  : <the ones that apply to the next step>
Drift    : none | <what differs and why it matters>
```

- If the user's message already says what to do, do that.
- Otherwise: if any Pending item ends in `waiting on: user`, ask about those first, in a single question. If none do, propose the first unticked item. Don't list every open decision at once.
- If the handoff is missing a required section (see `${CLAUDE_PLUGIN_ROOT}/docs/HANDOFF-FORMAT.md`), say so and read the whole file instead.
- Decisions recorded in the handoff stand. Don't reopen them unless you found evidence that they're wrong, and if you did, say what the evidence is.
- The handoff's `## Gotchas` apply to this session as rules.

## Other entry points

- **The user pasted a long text instead of a handoff:** work from it. At the end, suggest closing the source session with `/relay:handoff` next time so a pickup can replace the paste.
- **The handoff mentions a peer session or a pair thread:** continue with `/relay:peer <role> --of <name>` or `/relay:pair build <thread>`.
- **The handoff says "resume this exact session":** that command (`claude --resume <id>`) is for the user to run in a new terminal. You can't run it from inside this session.
