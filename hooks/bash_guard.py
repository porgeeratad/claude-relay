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

# .env files, except templates (.env.example) and source files named after them (.env.schema.ts, env.d.ts).
SECRET_FILE = (r"(?:\.env(?![\w-])(?!(?:\.[\w-]+)*\.(?:example|sample|template|dist)(?![\w-]))(?:\.[\w-]+)*"
               r"(?<!\.ts)(?<!\.js)(?<!\.mjs)(?<!\.cjs)(?<!\.py)(?<!\.go)(?<!\.rb)(?<!\.md)(?![.\w-])|"
               r"\.envrc\b|\.netrc\b|\.pgpass\b|\.npmrc\b|\.pypirc\b|"
               r"credentials(?:\.json)?(?:\.(?:bak|old|orig|save|backup))?(?![\w.])|"
               r"id_(?:rsa|ed25519|ecdsa)\b(?!\.pub))")
CLAUDE_CFG = r"(?:\.claude\.json|claude_desktop_config\.json)"
NAMES_ONLY = r"cut\s+-d\s*['\"]?=['\"]?\s+-f\s*1(?![-,\d])|\bgrep\s+-[a-zA-Z]*[cq]|\|\s*wc\b"
# Commands that print the files they are given.
READERS = {"cat", "head", "tail", "less", "more", "bat", "strings", "diff", "sdiff", "comm", "sort", "uniq",
           "awk", "gawk", "xxd", "od", "hexdump", "base64", "nl", "tac", "rev", "tr", "column", "paste"}
GREPS = {"grep", "egrep", "fgrep", "rg", "ag"}
# A later pipeline stage that keeps only names/counts makes the earlier read harmless.
NAMES_ONLY_STAGE = re.compile(r"^\s*(?:cut\b[^|]*-f\s*1(?![-,\d])|(?:e|f)?grep\s+(?:-[a-zA-Z]+\s+)*-[a-zA-Z]*[cqlL]|wc\b)")
# Strings run as commands elsewhere: their content is checked as a command of its own.
CARRIERS = (
    re.compile(r"\b(?:ba|z|da|k)?sh\s+(?:-\w+\s+)*-c\s+(['\"])((?:\\.|(?!\1).)*)\1", re.S),
    re.compile(r"\beval\s+(['\"])((?:\\.|(?!\1).)*)\1", re.S),
    re.compile(r"\bssh\b[^'\"|;&\n]*(['\"])((?:\\.|(?!\1).)*)\1", re.S),
)
TERMINAL = re.compile(r"/dev/(?:stdout|stderr|tty|fd/[12])$")
SUBSTITUTION = re.compile(r"[<>$]\(([^()]*)\)")  # <(...) >(...) $(...)
PREFIXES = {"sudo", "command", "time", "nice", "nohup", "exec", "env"}
QUOTED = re.compile(r"'([^']*)'|\"((?:\\.|[^\"\\])*)\"")
REDIRECT = re.compile(r"(\d*|&)(>>?|<)(&?)\s*([^\s|;&<>]+)")
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


def unquote(cmd, keep=None):
    """Replace quoted strings with '' (text *about* a command isn't the command).
    With `keep`, a quote that is just a path matching `keep` survives (`cat "$HOME/.env"`)."""
    def sub(m):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        if keep and re.fullmatch(r"[~$\w/ .{}()@+-]*" + keep, inner or ""):
            return m.group(0)
        return "''"
    return QUOTED.sub(sub, cmd)


def stage_prints(stage, target, readers):
    """True when one pipeline stage writes the contents of a `target` file to the terminal."""
    to_file = []

    def strip_redirect(m):
        fd, op, dup, dest = m.groups()
        if op == "<":
            return f" {dest} "                    # input file: still an argument for our purposes
        if fd in ("", "1", "&") and not dup and not TERMINAL.match(dest):
            to_file.append(dest)                 # stdout goes to a file, so nothing reaches the transcript
        return " "

    words = REDIRECT.sub(strip_redirect, stage).split()
    if to_file:
        return False
    lead = next((w for w in words if w not in PREFIXES and not re.match(r"^[A-Za-z_]\w*=", w)), "")
    if lead in ("echo", "printf"):               # `echo cat .env` prints the words, not the file
        return False
    # The reader can sit anywhere: `docker exec app cat .env`, `timeout 5 cat .env`, `kubectl exec p -- cat .env`.
    for i, word in enumerate(words):
        head = os.path.basename(word)
        if head not in readers and head not in GREPS and head not in ("sed", "cut"):
            continue
        args = words[i + 1:]
        short = "".join(a[1:] for a in args if re.match(r"^-[A-Za-z]", a))
        if head in GREPS:
            if re.search(r"[clqL]", short) or {"--count", "--files-with-matches", "--files-without-match",
                                               "--quiet", "--silent"} & set(args):
                return False
            if not re.search(r"[ef]", short):  # without -e/-f the first operand is the pattern, not a file
                args = [a for a in args if not a.startswith("-")][1:]
        elif head == "sed" and ("i" in short or any(a.startswith("--in-place") for a in args)):
            return False
        elif head == "cut" and re.search(r"-f\s*1(?![-,\d])", " ".join(args)):
            return False
        return any(re.search(target, a) for a in args)
    return False


def prints_file(cmd, target, readers, depth=0):
    """True when some pipeline prints the contents of a file matching `target`."""
    if depth < 3:
        for carrier in CARRIERS:                 # bash -c '...', eval '...', ssh host '...'
            for m in carrier.finditer(cmd):
                if prints_file(m.group(2), target, readers, depth + 1):
                    return True
        for m in SUBSTITUTION.finditer(cmd):     # judge each substitution on its own
            if prints_file(m.group(1), target, readers, depth + 1):
                return True
    text = unquote(SUBSTITUTION.sub(" _ ", cmd), keep=target)
    for pipeline in re.split(r"\|\||&&|[;\n]|(?<![>&<|])&(?![>&])", text):
        stages = pipeline.split("|")
        for i, stage in enumerate(stages):
            if stage_prints(stage, target, readers) and \
                    not any(NAMES_ONLY_STAGE.search(later) for later in stages[i + 1:]):
                return True
    return False


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
        files_only = unquote(cmd, keep=CLAUDE_CFG)
        if prints_file(cmd, CLAUDE_CFG, READERS):
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
    if prints_file(cmd, SECRET_FILE, READERS | {"jq"}) or (
            re.search(r"\b(python3?|node|ruby|perl)\b", cmd) and
            re.search(r"(open|read_text|read_bytes|readFileSync|readFile|File\.read)\s*\(\s*['\"][^'\"\n]*" +
                      SECRET_FILE + r"['\"](?!\s*,\s*['\"][wax])", body)):   # write/append modes don't print
        yield "S8", ("Reading a secret file prints its values. Names only: `cut -d= -f1 .env` · "
                     "presence: `grep -c '^NAME=' .env`.")

    # --- exit codes swallowed by a pipe ------------------------------------------
    bare = unquote(cmd)  # a commit message that mentions `tsc | tail` is not a pipeline
    if not re.search(r"pipefail|PIPESTATUS|pipestatus", cmd):
        tests = (r"\b(pytest|vitest|jest|npm\s+(run\s+)?test|pnpm\s+(run\s+)?test|yarn\s+test|bun\s+test|"
                 r"go\s+test|cargo\s+test|ruff\s+check|tsc|make\s+test)\b(?:[^;&|\n]|\d?>&\d)*\|(?!\|)")
        ship = (SEG_START +
                r"(?:git\s+(?:-C\s+\S+\s+)?(?:commit|push)\b|(?:npx\s+)?wrangler\s+deploy\b|"
                r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:deploy|publish|release)\b|npm\s+publish\b|"
                r"\S*scripts/(?:ship|deploy|release)\b)")
        if re.search(tests, bare, re.M) and re.search(ship, bare, re.M):
            yield "P1", ("Tests piped into tail/grep return the exit code of the last command, so the "
                         "commit/push/deploy runs even when tests fail. Run tests on their own first, "
                         "or prefix `set -o pipefail;`.")
        if re.search(SEG_START + r"gh\s+run\s+watch\b[^;&|\n]*\|(?!\|)", bare, re.M):
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
