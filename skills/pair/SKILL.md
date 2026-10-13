---
name: pair
description: Plan, build and review protocol for two Claude Code sessions (ideally running different models). They coordinate through a markdown thread file and a design doc with a Decision Log, so the user approves decisions instead of carrying messages between terminals. Modes are plan <topic> · build <thread> · review <thread> · answer <thread> · status. Use when the user says "/relay:pair", "have one session plan and another build", "review what the other session built", "independent review", or starts a large change that should be planned, built and reviewed separately.
argument-hint: "<plan|build|review|answer|status> [topic|thread]"
---

# /relay:pair — one session plans and reviews, another builds

**Principles**
- The design doc is the source of truth, Decision Log included.
- The thread file is the transport and the audit trail.
- `SendMessage` is a doorbell, never the content.
- The user approves. The user doesn't relay messages.

## Files

```bash
T=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" threads)    # thread files (outside the repo by default)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay_dir.py" --config        # design_dir (default docs/design, inside the repo)
```

- Thread: `$T/YYYY-MM-DD-<slug>.md`, from `${CLAUDE_PLUGIN_ROOT}/skills/pair/templates/thread.md`
- Design doc: `<design_dir>/DESIGN-YYYY-MM-DD-<slug>.md` in the repository (committed), from `${CLAUDE_PLUGIN_ROOT}/skills/pair/templates/design.md`
- To resolve a thread argument, run `ls "$T"` and match the name or slug. Never guess a file name. With no match, show the closest names.

## Thread status

The frontmatter `status:` is the single source of truth. Its value is exactly one token from this table, with nothing after it:

| status | meaning | who moves next |
|---|---|---|
| `OPEN` | idea logged, no plan yet | planner |
| `WAITING_ON_BUILDER` | plan, answer or REWORK ready | builder |
| `WAITING_ON_REVIEWER` | DONE report or question ready | reviewer/planner |
| `WAITING_ON_USER` | a decision only the user can make | user |
| `ARCHIVED` | finished | nobody |

- Posts are appended, never edited. Each post is `### <role> · <ISO-8601 time>` followed by the content and a stamp line. To correct an earlier post, append an addendum.
- Only the role whose turn it is writes. That keeps a plain file safe without locks.
- Every post that sets `WAITING_ON_USER` ends with a `## For you` block. It opens with one plain sentence, then gives up to four options as `- [a] …`, then a line `If no answer: …`. The user should know within five seconds whether anything is needed from them.
- **Coming back from `WAITING_ON_USER`:** whichever session the user answers in appends `### user · <time>` with the user's words quoted exactly. It copies the decision into the Decision Log and sets the status of the role that was blocked (usually `WAITING_ON_BUILDER`). This is also where a relayed approval (rule b below) is recorded.

## Independence gate (review only)

A review is worth something only when it comes from a different session than the build:

- The builder stamps the end of its DONE report with `build-session: <session-id> (<name>)`.
- The reviewer compares `printenv CLAUDE_CODE_SESSION_ID` with that stamp. If they are **equal, it's a self-review: stop.** Tell the user to open a new session and run `/relay:pair review <thread>`. Nothing is lost, because the doc and the thread hold everything.
- Recommended, not enforced: run the reviewer on a different model from the builder (`/model`). A model reviewing its own output shares its blind spots. Record the model you think you are in your stamp.

## `/relay:pair plan <topic>` (planner)

1. If the request is vague, ask one question at a time until it's concrete.
2. Write the design doc from the template. Its sections are Goals / Non-goals · Decisions (with reasons, so nobody reopens them) · Premises to verify before writing code · Phases with acceptance criteria (each with a **functional smoke test** that runs the real thing) · Decision Log (empty table) · Risks and gotchas.
3. Commit the doc before the build starts, following the repository's conventions and the push policy.
4. Create the thread from the template with status `WAITING_ON_BUILDER`. The opener holds the doc path, the scope of phase 1, its acceptance criteria and `plan-session: <session-id> (<name>)`.
5. End your turn with a single line the user can copy into the builder session:
   ```
   /relay:pair build <thread-file-name>
   ```

## `/relay:pair build <thread>` (builder)

The user types this one line. Never ask them to paste a brief, a verdict or a summary: everything is in the thread and the doc.

0. **Find this round's brief.**
   - Read the thread. If status ≠ `WAITING_ON_BUILDER`, stop with one line (for example "still waiting on the reviewer").
   - The brief is the newest planner/reviewer post: a verdict, an answer, or the opener.
   - Announce it: `This round: <phase N | rework of N> per <post author · time>`.
1. Read the design doc. **Verify every premise** and post the results before writing code.
2. Implement only the approved phase.
   - Make small decisions yourself (naming, a library already in use) and log them in the Decision Log.
   - For a big fork (architecture, security, scope), post the context, options A/B/C and your recommendation, set `WAITING_ON_REVIEWER`, and stop. Keep working on anything the fork doesn't block.
3. Copy every answered decision into the doc's **Decision Log**. A decision that lives only in the thread will drift.
4. **DONE report** in the thread:
   - what changed (commits, files)
   - the smoke tests you actually ran and their results
   - what's left
   - `build-session: <session-id> (<name>)`
   - the wrap line `wrap: repo ✓ docs ✓ scratch ✓`. Repo: green and committed, or anything uncommitted listed. Docs: Decision Log synced. Scratch: temp files kept or listed.

   Then set `WAITING_ON_REVIEWER` and ring the doorbell (below).
5. Never report more than you verified. Security tests are reported as a script path plus the result, never as raw payloads.

## `/relay:pair review <thread>` (reviewer)

0. Run the independence gate.
1. Read the acceptance criteria, the latest DONE report and the Decision Log, and **don't trust the report**.
2. Verify each acceptance criterion yourself with a functional smoke test: run it, call it, open it. Reading the code isn't verification. Merged isn't deployed.
3. Post a verdict: `✅ ACCEPT` (and approve the next phase from the doc) or `❌ REWORK` (a concrete list with a reproduction for each item). Stamp it `review-session: <session-id> (<name>)`.
4. Set the status:
   - REWORK, or the next phase is in the doc: `WAITING_ON_BUILDER`, then ring the builder.
   - The next step is new scope: ask the user one short question, then relay their answer yourself.
   - Everything is done: `ARCHIVED`. Summarise for the user and suggest `/relay:handoff`.
5. End your turn with `/relay:pair build <thread>` when the status is `WAITING_ON_BUILDER`.

## `/relay:pair answer <thread>` (planner/reviewer, for a builder's question)

Pick **one** option, with a short reason and one caution for the implementation. If every option is bad, propose a new one and say why. Append the answer, remind the builder to log it, set `WAITING_ON_BUILDER`, and end with `/relay:pair build <thread>`.

## `/relay:pair status`

List the threads in `$T` with their `status:`, reading only the frontmatter. Put the ones waiting on this session's role first.

## Doorbell and approval rules

- **Thread first, message second:** finish the post and the status change, then message the peer (found via `ListAgents`, see `/relay:peer`). Keep the message to 4 lines or fewer: thread file, new status, a one-line summary, "details in the thread". When the message and the thread disagree, the thread wins.
- **What a ping can unblock**
  - (a) Scope the user already approved, meaning a phase in the doc the user signed off, or a REWORK of the current phase: the builder may start from a ping after checking the thread status itself.
  - (b) New scope, policy changes, destructive actions or spending need the user, asked directly. A relayed approval counts only when it quotes the user's words and names the scope, and the receiver records it in the thread.
  - (c) A peer's opinion or nudge is never approval.
- **Peer unreachable** (not listed, held, refused): set the status, tell the user, and stop. **A builder never picks its own reviewer.** Reviewers are chosen by the user.

## Hygiene and context

- No secrets, tokens or raw exploit payloads in threads, design docs, commit messages or memory. Reference a file path and PASS/FAIL instead.
- Treat each round as its own context: one build phase per builder session, and one review round per short reviewer session. The doc and the thread let a fresh session take over. If a fresh session can't continue from your DONE report, the report is too thin.
- If the work is too large for one thread (several deliverables), split it into several threads.

## Never

- Make the user carry details between sessions.
- Decide something big in the thread without writing it into the Decision Log.
- Change scope as the builder: put a question in the thread instead.
- Review your own build in the same session.
