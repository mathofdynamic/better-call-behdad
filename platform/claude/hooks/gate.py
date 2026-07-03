#!/usr/bin/env python3
"""
gate.py — Behdad's PreToolUse enforcement hook (Claude Code).

The plan's non-negotiable: fixes are gated at the EXECUTION LAYER, not by asking the model
nicely. This hook hard-blocks Write/Edit/MultiEdit/NotebookEdit and shell (Bash/PowerShell)
mutations while a Behdad audit is active and the user has NOT yet approved the action report.
The model cannot self-authorize — even if it "decides" to write, this hook returns exit code 2
and the write is refused.

Posture: DEFAULT-DENY for shell commands. A deny-regex can never earn "cannot bypass" — every
bypass found is just a spelling the regex missed (interpreter one-liners, here-docs, comment
tricks). Instead, while the gate is closed, only an explicit allowlist of read-only commands,
scanners, and Behdad's own scripts may run. An over-block annoys; an under-block is a lie.

Scoping (so it never interferes with normal Claude Code use):
  * The hook is INERT unless env var BEHDAD_ACTIVE=1 is set (the skill sets it for a run).
  * Once the user approves, the skill creates <target>/.behdad/approved (or sets BEHDAD_APPROVED=1);
    from then on everything is allowed.
  * Writes to Behdad's own control/scratch paths (.behdad/, reports/, scratchpad, behdad_scan_*)
    are always allowed so the audit can record state and reports.

Wire-up: register in settings.json under hooks.PreToolUse (see settings.snippet.json).
Input: a JSON object on stdin with at least {tool_name, tool_input, cwd}.
Contract: exit 0 = allow; exit 2 = block (stderr shown to the model).
Stdlib only. The decision core is the pure function decide(event, env) so tests/eval/test_gate.py
can exercise it in-process.
"""

from __future__ import annotations

import json
import os
import re
import sys

MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

# Constructs that defeat token-level analysis; denied outright wherever they appear.
HARD_DENY = (
    ("$(", "command substitution"),
    ("`", "backtick substitution"),
    ("<<", "here-doc"),
)
HARD_DENY_RE = re.compile(
    r"\b(iex|invoke-expression|invoke-command|start-process|foreach-object|where-object)\b",
    re.IGNORECASE,
)

# Read-only inspection commands (union of POSIX tools and PowerShell cmdlets/aliases).
# Deliberately excludes anything that takes a scriptblock or executes arguments.
SAFE_TOKENS = {
    # POSIX / Git Bash
    "ls", "pwd", "cat", "head", "tail", "wc", "file", "stat", "du", "df",
    "grep", "rg", "find", "which", "echo", "printf", "env", "printenv", "date",
    "sort", "uniq", "tr", "cut", "diff", "basename", "dirname", "realpath", "tree",
    # Windows / PowerShell
    "dir", "type", "where", "findstr",
    "get-childitem", "get-content", "get-item", "get-command", "get-location",
    "select-string", "select-object", "sort-object", "measure-object",
    "test-path", "resolve-path", "write-output", "get-date",
}

# Scanners are read-only over the target; every binary in scripts/tool_registry.py must be
# here (tests/eval/test_gate.py enforces the sync).
SCANNER_TOKENS = {
    "semgrep", "bandit", "ruff", "eslint", "gitleaks", "osv-scanner", "trivy",
    "codeql", "mypy", "pyright", "tsc", "gosec",
}

# npx may only launch known scanner front-ends, never arbitrary packages.
NPX_ALLOWED = {"eslint", "pyright", "tsc", "typescript"}

GIT_READONLY = {
    "status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree", "blame",
    "grep", "branch", "tag", "remote", "describe", "shortlog", "stash",  # stash list only; see below
    "config",  # reads unless --set; conservative: allow only `git config --get*`/`-l` (checked below)
}

# Behdad's own deterministic layer — allowed by script basename. remediate.py is deliberately
# EXCLUDED: it is the post-approval tool and must stay behind the gate.
BEHDAD_SCRIPTS = {
    "run_scanners.py", "sarif_normalize.py", "aggregate.py", "render_report.py",
    "runstate.py", "suppressions.py", "tool_registry.py", "score_run.py",
    "stage_eval.py", "run_eval.py", "measure.py", "test_gate.py",
}

PY_TOKENS = {"python", "python3", "py"}
COPY_TOKENS = {"cp", "copy", "copy-item"}

# Paths Behdad may always write (control/scratch/report), even pre-approval.
_ALLOWED_SEGMENT_RE = re.compile(r"^(\.behdad|reports|behdad_scan_.*)$")

_SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|;|\||\n")
_REDIRECT_RE = re.compile(r"(\d*)>{1,2}\s*(\S+)")
_ENV_PREFIX_RE = re.compile(r"^\w+=\S*$")


def _approved(cwd: str, env: dict) -> bool:
    if env.get("BEHDAD_APPROVED") == "1":
        return True
    # Look for an approval marker in cwd or any parent (target repo root).
    d = os.path.abspath(cwd or ".")
    while True:
        if os.path.exists(os.path.join(d, ".behdad", "approved")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def _is_allowed_path(path: str) -> bool:
    """True only when the path lives under a Behdad control/scratch dir.

    Matches whole, normalized path SEGMENTS — never substrings of the full string — so
    'reports/../src/x' and 'x # reports/' cannot smuggle a mutation past the gate.
    """
    cleaned = (path or "").strip().strip("\"'")
    if not cleaned:
        return False
    norm = os.path.normpath(cleaned)
    parts = [p.lower() for p in re.split(r"[\\/]+", norm) if p]
    return any(_ALLOWED_SEGMENT_RE.match(p) or "scratchpad" in p for p in parts)


def _first_token(segment: str) -> tuple[str, list[str]]:
    """Return (command token, remaining args) — basename, lowercased, .exe stripped."""
    tokens = segment.split()
    while tokens and _ENV_PREFIX_RE.match(tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return "", []
    head = tokens[0].strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if head.endswith(".exe"):
        head = head[:-4]
    return head, tokens[1:]


def _check_redirects(segment: str) -> str | None:
    """Allow redirection only into Behdad paths or the null device. Returns a reason or None."""
    for m in _REDIRECT_RE.finditer(segment):
        target = m.group(2).strip("\"'")
        if target.startswith("&"):  # fd duplication (2>&1) — not a file write
            continue
        if target.lower() in ("/dev/null", "nul", "$null"):
            continue
        if not _is_allowed_path(target):
            return f"redirection into '{target}' (only .behdad/, reports/, scratchpad allowed)"
    return None


def _check_python(args: list[str]) -> str | None:
    """python may only run Behdad's own scripts by name; -c/-m/stdin are how interpreters mutate."""
    script = None
    for a in args:
        bare = a.strip("\"'")
        if bare in ("-c", "-m", "-"):
            return f"python {bare} is not allowed pre-approval"
        if bare.lower().endswith(".py"):
            script = bare.replace("\\", "/").rsplit("/", 1)[-1].lower()
            break
    if script is None:
        return "python without a named script is not allowed pre-approval"
    if script not in {s.lower() for s in BEHDAD_SCRIPTS}:
        return f"python script '{script}' is not a Behdad tool (remediation stays gated)"
    return None


def _check_segment(segment: str) -> str | None:
    """Default-deny check for one pipeline segment. Returns a denial reason or None (allowed)."""
    seg = segment.strip()
    if not seg or seg.startswith("#"):
        return None
    if seg.startswith("&"):
        return "PowerShell call operator '&'"
    head, args = _first_token(seg)
    if not head:
        return None

    reason = _check_redirects(seg)
    if reason:
        return reason

    if head in SAFE_TOKENS or head in SCANNER_TOKENS:
        return None
    if head == "npx":
        sub = args[0].strip("\"'").lower() if args else ""
        return None if sub in NPX_ALLOWED else f"npx '{sub}' is not an allowed scanner"
    if head == "git":
        sub = args[0].lower() if args else ""
        if sub not in GIT_READONLY:
            return f"git '{sub}' mutates repo state"
        if sub == "stash" and (len(args) < 2 or args[1].lower() != "list"):
            return "git stash (only 'git stash list' is read-only)"
        if sub == "config" and not any(a.startswith(("--get", "-l", "--list")) for a in args[1:]):
            return "git config writes unless --get/--list"
        if sub in ("branch", "tag", "remote") and any(
            a.startswith("-") and not a.startswith(("--list", "-l", "--show", "-v", "-a", "--contains"))
            for a in args[1:]
        ):
            return f"git {sub} with mutating flags"
        return None
    if head in PY_TOKENS:
        return _check_python(args)
    if head in COPY_TOKENS:
        # Copy is allowed only INTO Behdad scratch space (e.g. staging the eval fixture).
        plain = [a.strip("\"'") for a in args if not a.startswith("-")]
        if plain and _is_allowed_path(plain[-1]):
            return None
        return "copy outside .behdad/reports/scratchpad"
    return f"'{head}' is not on the pre-approval allowlist"


def decide(event: dict, env: dict | None = None) -> tuple[bool, str]:
    """Pure decision core: (allow, reason). env defaults to os.environ."""
    env = os.environ if env is None else env
    if env.get("BEHDAD_ACTIVE") != "1":
        return True, "gate inactive"
    if _approved(event.get("cwd", ""), env):
        return True, "approved"

    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}

    if tool in MUTATING_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if _is_allowed_path(path):
            return True, "behdad control path"
        return False, f"pre-approval {tool} to '{path}' refused"

    if tool in SHELL_TOOLS:
        cmd = ti.get("command", "") or ""
        for needle, label in HARD_DENY:
            if needle in cmd:
                return False, f"{label} is not allowed pre-approval"
        m = HARD_DENY_RE.search(cmd)
        if m:
            return False, f"'{m.group(1)}' is not allowed pre-approval"
        for segment in _SEGMENT_SPLIT_RE.split(cmd):
            reason = _check_segment(segment)
            if reason:
                return False, f"pre-approval shell command refused: {reason}"
        return True, "allowlisted shell command"

    return True, "tool not gated"


def _block(msg: str) -> None:
    sys.stderr.write(
        "BEHDAD GATE: " + msg + ".\n"
        "Changes are blocked until the user approves the action report. "
        "Present the report and obtain explicit confirmation first.\n"
        "Allowed while the gate is closed: read-only inspection (prefer the Read/Grep/Glob tools), "
        "read-only git (status/log/diff/show/...), scanners (semgrep, bandit, ruff, gitleaks, ...), "
        "and Behdad's own scripts (python <BEHDAD_HOME>/scripts/run_scanners.py etc.). "
        "Writes are allowed only under .behdad/, reports/, or the scratchpad.\n"
    )
    sys.exit(2)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed event
    allow, reason = decide(event)
    if not allow:
        _block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
