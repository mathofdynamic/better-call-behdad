#!/usr/bin/env python3
"""
gate.py — Behdad's PreToolUse enforcement hook (Claude Code).

The plan's non-negotiable: fixes are gated at the EXECUTION LAYER, not by asking the model
nicely. This hook hard-blocks Write/Edit/MultiEdit/NotebookEdit/Bash mutations while a Behdad
audit is active and the user has NOT yet approved the action report. The model cannot
self-authorize — even if it "decides" to write, this hook returns exit code 2 and the write is
refused.

Scoping (so it never interferes with normal Claude Code use):
  * The hook is INERT unless env var BEHDAD_ACTIVE=1 is set (the skill sets it for a run).
  * Once the user approves, the skill creates <target>/.behdad/approved (or sets BEHDAD_APPROVED=1);
    from then on writes are allowed.
  * Writes to Behdad's own control/scratch paths (.behdad/, reports/, scratchpad) are always allowed
    so the audit can record state and reports.

Wire-up: register in settings.json under hooks.PreToolUse (see settings.snippet.json).
Input: a JSON object on stdin with at least {tool_name, tool_input, cwd}.
Contract: exit 0 = allow; exit 2 = block (stderr shown to the model).
Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys

MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# Bash commands that modify the filesystem / repo state (best-effort heuristic).
BASH_WRITE_RE = re.compile(
    r"""(^|\s|;|\||&)(         # command boundary
        rm|mv|cp|dd|truncate|tee|
        sed\s+-i|perl\s+-i|
        git\s+(commit|apply|checkout|reset|restore|clean|rebase|merge|push|mv|rm)|
        npm\s+(install|i|ci|uninstall)|pip\s+(install|uninstall)|
        chmod|chown|mkdir|rmdir|touch|
        >\s*\S|>>\s*\S            # output redirection into a file
    )(\s|$)""",
    re.IGNORECASE | re.VERBOSE,
)

# Paths Behdad may always write (control/scratch/report), even pre-approval.
ALLOW_SUBSTRINGS = (".behdad", "/reports/", "\\reports\\", "scratchpad", "behdad_scan_")


def _approved(cwd: str) -> bool:
    if os.environ.get("BEHDAD_APPROVED") == "1":
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
    p = (path or "").replace("\\", "/").lower()
    return any(s.replace("\\", "/").lower() in p for s in ALLOW_SUBSTRINGS)


def _block(msg: str) -> None:
    sys.stderr.write(
        "BEHDAD GATE: " + msg +
        "\nChanges are blocked until the user approves the action report. "
        "Present the report and obtain explicit confirmation first.\n"
    )
    sys.exit(2)


def main() -> int:
    # Inert unless a Behdad run is active.
    if os.environ.get("BEHDAD_ACTIVE") != "1":
        return 0

    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed event

    if _approved(event.get("cwd", "")):
        return 0

    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}

    if tool in MUTATING_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if _is_allowed_path(path):
            return 0
        _block(f"pre-approval {tool} to '{path}' refused.")

    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if BASH_WRITE_RE.search(cmd) and not _is_allowed_path(cmd):
            _block(f"pre-approval mutating shell command refused: {cmd[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
