#!/usr/bin/env python3
"""PreToolUse(Bash) guard: blocks a small set of shell habits that leak secrets
into the transcript or hide a failing exit code.

Why a hook and not a rule in CLAUDE.md: written rules get broken again and again
under pressure; a hook is enforced on every call.

Contract
- Reads the PreToolUse JSON on stdin; answers with a JSON decision on stdout.
- Fail-open: any internal error means "no decision" (the call proceeds).
- Stdlib only, no network, no file reads.

Configuration (environment of the Claude Code process, e.g. "env" in settings.json)
- RELAY_GUARD_OFF   comma-separated rule ids to disable, or "all"   (e.g. "S5,K1")
- RELAY_GUARD_MODE  "deny" (default) or "ask" (prompt instead of blocking)
"""
import json
import os
import re
import sys

I = re.I

SECRET_FILE = (r"(?:\.env(?!\.(?:example|sample|template|dist)\b)(?:\.[\w.-]+)?\b|\.netrc\b|"
               r"\.pgpass\b|\.npmrc\b|\.pypirc\b|credentials(?:\.json)?\b|id_(?:rsa|ed25519|ecdsa)\b(?!\.pub))")
CLAUDE_CFG = r"(?:\.claude\.json|claude_desktop_config\.json)"
NAMES_ONLY = r"cut\s+-d\s*['\"]?=['\"]?\s+-f\s*1(?![-,\d])|\bgrep\s+-[a-zA-Z]*[cq]|\|\s*wc\b"
SEG_START = r"(?:^|[;&|(]\s*|\$\(\s*|\bthen\s+|\bdo\s+)"

RULES = {
    "S1": "claude mcp list/get",
    "S2": "raw read of ~/.claude.json",
    "S3": "/proc/*/environ dump",
    "S4": "docker inspect without --format",
    "S5": "environment dump",
    "S6": "sed redaction without -n",
    "S7": "grep -v used as redaction",
    "S8": "raw read of a secret file",
    "P1": "piped tests followed by commit/push/deploy",
    "P2": "piped gh run watch",
    "K1": "broad pkill -f",
}


def strip_heredoc_bodies(cmd):
    """Drop heredoc bodies so text being *written* (docs, scripts) doesn't trip the rules."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        m = re.search(r"<<-?\s*\\?(['\"]?)([A-Za-z_]\w*)\1", lines[i])
        if m:
            i += 1
            while i < len(lines) and lines[i].strip() != m.group(2):
                i += 1
        i += 1
    return "\n".join(out)


def jq_filters(cmd):
    for m in re.finditer(r"\bjq\b(?:\s+-[\w-]+)*\s+(['\"])(.*?)\1", cmd, re.S):
        yield m.group(2)
    for m in re.finditer(r"\bjq\b(?:\s+-[\w-]+)*\s+([^\s'\"|;&-][^\s|;&]*)", cmd):
        yield m.group(1)


def rules(cmd, body):
    """Yield (rule_id, reason). `cmd` has heredoc bodies stripped; `body` is the full text."""
    # --- secrets in the transcript ------------------------------------------------
    if re.search(r"\bclaude\s+mcp\s+(list|get)\b", cmd):
        yield "S1", ("`claude mcp list/get` can print MCP server headers and tokens. "
                     "List names with `jq '.mcpServers | keys' ~/.claude.json`.")

    if re.search(CLAUDE_CFG, cmd):
        # A quoted string is a pattern or replacement, not a file argument, unless it IS the path.
        files_only = re.sub(r"'([^']*)'|\"([^\"]*)\"",
                            lambda m: m.group(0)
                            if re.fullmatch(r"[~$\w/ .{}()-]*" + CLAUDE_CFG, m.group(1) or m.group(2) or "")
                            else "''", cmd)
        if re.search(r"\b(cat|less|more|head|tail|bat|strings|sed|awk)\b[^|;&\n]*" + CLAUDE_CFG, files_only) or \
           re.search(r"\bgrep\b(?![^|;&\n]*\s-[a-zA-Z]*[clqL]\b)[^|;&\n]*" + CLAUDE_CFG, files_only):
            yield "S2", ("~/.claude.json holds MCP tokens; reading it raw puts them in the transcript. "
                         "Use jq on non-secret fields, e.g. `jq '.mcpServers | keys' ~/.claude.json`.")
        elif re.search(r"\bjq\b[^|;&\n]*" + CLAUDE_CFG, files_only) or \
                re.search(CLAUDE_CFG + r"[^;&\n]*\|\s*jq\b", files_only):
            safe = re.compile(r"keys|\.args\b|\.command\b|\.type\b|length|has\(|\.url\b|\.cwd\b|\.model\b")
            filters = list(jq_filters(cmd))
            if not filters or not all(safe.search(f) for f in filters):
                yield "S2", ("jq on ~/.claude.json must select non-secret fields only "
                             "(keys, .command, .args, .url, .type, length).")
    if re.search(r"\b(python3?|node|ruby|perl)\b[^|;&\n]*" + CLAUDE_CFG, cmd) or \
       re.search(r"\b(python3?|node|ruby|perl)\s+(-\w+\s+)*-[ce]\s[^\n]*" + CLAUDE_CFG, cmd) or \
       (re.search(r"\b(python3?|node)\b[^\n]*<<", cmd) and   # heredoc script: only an actual open/load counts
            re.search(r"(open|read_text|read_bytes|load|readFileSync|require|Path)\s*\([^)\n]*" + CLAUDE_CFG, body)):
        yield "S2", ("Reading ~/.claude.json from a script prints MCP tokens just like cat. "
                     "Use jq on non-secret fields instead.")

    if re.search(r"/proc/[^\s/]+/environ", cmd) and not re.search(
            NAMES_ONLY + r"|grep\s+-oE?\s+['\"]\^\[A-Z_\]\[A-Z0-9_\]\*=['\"]", cmd):
        yield "S3", ("/proc/<pid>/environ holds runtime secrets (multi-line values survive `tr | cut`). "
                     "Names only: `tr '\\0' '\\n' < /proc/PID/environ | grep -oE '^[A-Z_][A-Z0-9_]*='`.")

    for m in re.finditer(r"\bdocker\s+(container\s+)?inspect\b", cmd):
        seg = re.split(r";|&&|\|\||\n", cmd[m.start():], maxsplit=1)[0]
        if re.search(r"Config\.Env|\.Env\b", seg) and not re.search(r"cut\s+-d\s*['\"]?=['\"]?\s+-f\s*1(?![-,\d])|\bkeys\b", seg):
            yield "S4", "docker inspect .Config.Env prints every env value. Cut to names with `| cut -d= -f1`."
            break
        if not re.search(r"\s(-f|--format)\b", seg):
            yield "S4", ("docker inspect without --format prints the whole Env block. "
                         "Select a field: `docker inspect --format '{{.State.Status}}' NAME`.")
            break

    if (re.search(SEG_START + r"(env|printenv|export\s+-p|set)\s*($|[|;&)>])", cmd, re.M) or
            re.search(r"\b(exec|run)\b[^|;&\n]*\s(env|printenv)\s*($|[|;&>'\"])", cmd, re.M) or
            re.search(r"\bssh\s+[^|;&\n]*['\"\s](env|printenv)\s*($|[|;&>'\"])", cmd, re.M)) and \
            not re.search(NAMES_ONLY, cmd):
        yield "S5", ("Dumping the environment prints every token in it. Names only: `env | cut -d= -f1` · "
                     "one variable: `[ -n \"${VAR-}\" ] && echo set`.")
    if re.search(r"\bprintenv\s+\w*(TOKEN|SECRET|KEY|PASS|WEBHOOK|AUTH)\w*", cmd, I):
        yield "S5", "printenv of a secret prints its value. Check presence: `[ -n \"${VAR-}\" ] && echo set len=${#VAR}`."

    if re.search(r"\bsed\b(?![^|;&\n]*\s-[a-zA-Z]*n)[^|;&\n]*?\bs([/|#,@])(?:(?!\1).)*\1(?:(?!\1).)*"
                 r"(REDACTED|\*\*\*|<redacted>|<masked>|<hidden>)", cmd, I):
        yield "S6", ("A sed redaction without -n prints every line it fails to match, raw secret included. "
                     "Fail closed: `sed -n 's/.../.../p'`.")
    if re.search(r"\bgrep\s+(?:-[a-zA-Z]+\s+)*-[a-zA-Z]*v[a-zA-Z]*\s+(?:-[a-zA-Z]+\s+)*(['\"]?)"
                 r"[^'\"\s|;&]*(key|token|secret|webhook|passw)[^'\"\s|;&]*\1(?:\s|$)", cmd, I):
        yield "S7", ("grep -v is not redaction: any secret whose line doesn't match the pattern gets printed. "
                     "Print names only, e.g. `cut -d= -f1 FILE`.")
    if re.search(r"\b(cat(?!\s*>)|head|tail|less|more|bat|strings)\b[^|;&\n>]*" + SECRET_FILE, cmd):
        yield "S8", ("Opening a secret file prints its values. Names only: `cut -d= -f1 .env` · "
                     "presence: `grep -c '^NAME=' .env`.")

    # --- exit codes swallowed by a pipe ------------------------------------------
    if not re.search(r"pipefail|PIPESTATUS|pipestatus", cmd):
        tests = (r"\b(pytest|vitest|jest|npm\s+(run\s+)?test|pnpm\s+(run\s+)?test|yarn\s+test|bun\s+test|"
                 r"go\s+test|cargo\s+test|ruff\s+check|tsc|make\s+test)\b(?:[^;&|\n]|\d?>&\d)*\|(?!\|)")
        ship = (SEG_START +
                r"(?:git\s+(?:-C\s+\S+\s+)?(?:commit|push)\b|(?:npx\s+)?wrangler\s+deploy\b|"
                r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:deploy|publish|release)\b|npm\s+publish\b|"
                r"\S*scripts/(?:ship|deploy|release)\b)")
        if re.search(tests, cmd, re.M) and re.search(ship, cmd, re.M):
            yield "P1", ("Tests piped into tail/grep return the exit code of the last command, so the "
                         "commit/push/deploy runs even when tests fail. Run tests on their own first, "
                         "or prefix `set -o pipefail;`.")
        if re.search(SEG_START + r"gh\s+run\s+watch\b[^;&|\n]*\|(?!\|)", cmd, re.M):
            yield "P2", ("`gh run watch | tail` always returns tail's exit code. Use "
                         "`gh run watch <id> --exit-status` unpiped, then `gh run view <id> --json conclusion`.")

    # --- processes -----------------------------------------------------------------
    for m in re.finditer(r"\bpkill\s+(?:-\w+\s+)*-[a-zA-Z]*f[a-zA-Z]*\s+(?:-\w+\s+)*(?:(['\"])(.*?)\1|(\S+))", cmd):
        pat = m.group(2) if m.group(2) is not None else m.group(3)
        if re.search(r"\d{3,}|/", pat) or len(pat.split()) >= 3:
            continue
        yield "K1", ("`pkill -f` with a broad pattern also kills processes of other sessions and tools. "
                     "Keep the PID you started (`$!`) and `kill <pid>`, or match a port/path.")
        break


def disabled():
    raw = os.environ.get("RELAY_GUARD_OFF", "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def decide(cmd):
    off = disabled()
    if "ALL" in off:
        return None
    hits = [(rid, msg) for rid, msg in rules(strip_heredoc_bodies(cmd), cmd) if rid not in off]
    if not hits:
        return None
    seen, parts = set(), []
    for rid, msg in hits:
        if (rid, msg) not in seen:
            seen.add((rid, msg))
            parts.append(f"[relay guard {rid}] {msg}")
    decision = "ask" if os.environ.get("RELAY_GUARD_MODE", "").lower() == "ask" else "deny"
    reason = " | ".join(parts) + f" (disable with RELAY_GUARD_OFF={hits[0][0]})"
    return decision, reason


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return
        cmd = (data.get("tool_input") or {}).get("command") or ""
        res = decide(cmd)
        if not res:
            return
        decision, reason = res
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason}}))
    except Exception:
        return


if __name__ == "__main__":
    main()
