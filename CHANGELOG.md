# Changelog

## 0.1.0 — 2026-10-13

- `/relay:handoff`: sweep → commit → handoff file → honest receipt + NEXT-CMD, delta mode on re-run
- `/relay:pickup`: latest handoff → verify against git → continue from Pending
- `/relay:peer`: cross-session handshake with role behaviour (assist waits)
- `/relay:pair`: plan / build / review / answer / status over a thread file + design doc, session-independence gate
- bash guard hook: S1–S8 secret leaks (segment-aware: grep/diff/sort/awk/jq…, quoted text and file redirects ignored), P1–P2 swallowed exit codes, K1 broad pkill; `RELAY_GUARD_OFF`, `RELAY_GUARD_MODE`
- `scripts/relay_dir.py`: one resolver for handoff/thread/state directories (`RELAY_DIR`, `.claude/relay.json`, XDG default)
