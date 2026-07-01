"""
tool_registry.py — Behdad's deterministic-scanner catalog and availability detector.

Both research efforts agreed the single highest-leverage lever for precision is grounding
LLM findings in real scanner output. This module knows which scanners exist, how to invoke
them headlessly, and — critically — degrades gracefully when a tool is missing (loud caveat,
never silent). It has no third-party dependencies (stdlib only) so it runs anywhere Python does.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tool:
    id: str
    # Executable name to look up on PATH.
    binary: str
    # What signal class this tool provides.
    kind: str  # "sast" | "sca" | "secrets" | "quality" | "types" | "iac"
    # Output format the runner should expect.
    output: str  # "sarif" | "json"
    # Languages/ecosystems it covers (for reporting; routing is by file globs in the runner).
    languages: list[str] = field(default_factory=list)
    # Human-facing install hint shown when the tool is absent.
    install: str = ""
    # Whether the tool executes/imports project code (unsafe on untrusted repos) — gated off
    # by default so a plain scan never runs arbitrary target code.
    executes_code: bool = False
    # Whether the tool is slow / needs setup (e.g. CodeQL DB build) — skipped in `quick` depth.
    slow: bool = False


# The catalog. Command construction lives in run_scanners.py; this is the metadata + detection.
TOOLS: dict[str, Tool] = {
    "semgrep": Tool(
        id="semgrep", binary="semgrep", kind="sast", output="sarif",
        languages=["python", "javascript", "typescript", "go", "java", "ruby", "php", "c", "generic"],
        install="pip install semgrep   (or: brew install semgrep)",
    ),
    "bandit": Tool(
        id="bandit", binary="bandit", kind="sast", output="json",
        languages=["python"],
        install="pip install bandit",
    ),
    "ruff": Tool(
        id="ruff", binary="ruff", kind="quality", output="json",
        languages=["python"],
        install="pip install ruff",
    ),
    "eslint": Tool(
        id="eslint", binary="eslint", kind="quality", output="json",
        languages=["javascript", "typescript"],
        install="npm install -g eslint   (needs an eslint config in the target repo)",
    ),
    "gitleaks": Tool(
        id="gitleaks", binary="gitleaks", kind="secrets", output="json",
        languages=["*"],
        install="https://github.com/gitleaks/gitleaks#installing  (or: brew install gitleaks)",
    ),
    "osv-scanner": Tool(
        id="osv-scanner", binary="osv-scanner", kind="sca", output="json",
        languages=["*"],
        install="https://google.github.io/osv-scanner/installation/  (go install ...)",
    ),
    "trivy": Tool(
        id="trivy", binary="trivy", kind="sca", output="sarif",
        languages=["*"],
        install="https://aquasecurity.github.io/trivy/  (or: brew install trivy)",
    ),
    # --- Advanced / gated tools (not auto-run in a default scan) ---
    "codeql": Tool(
        id="codeql", binary="codeql", kind="sast", output="sarif",
        languages=["python", "javascript", "typescript", "go", "java", "cpp", "csharp", "ruby"],
        install="https://github.com/github/codeql-cli-binaries/releases",
        slow=True,  # requires DB build; only in `thorough` depth
    ),
    # Type-checkers import/analyze code; treated as ground truth for the logic inspector but
    # gated because they can execute import-time side effects in the target project.
    "mypy": Tool(
        id="mypy", binary="mypy", kind="types", output="json",
        languages=["python"], install="pip install mypy", executes_code=True,
    ),
    "pyright": Tool(
        id="pyright", binary="pyright", kind="types", output="json",
        languages=["python"], install="npm install -g pyright", executes_code=True,
    ),
    "tsc": Tool(
        id="tsc", binary="tsc", kind="types", output="json",
        languages=["typescript"], install="npm install -g typescript", executes_code=True,
    ),
}


def detect() -> dict[str, bool]:
    """Return {tool_id: is_available} by probing PATH."""
    return {tid: shutil.which(t.binary) is not None for tid, t in TOOLS.items()}


def available_tools(*, allow_code_execution: bool = False, allow_slow: bool = False) -> list[Tool]:
    """
    Tools that are installed AND permitted under the current safety/depth settings.
    By default excludes code-executing tools (unsafe on untrusted repos) and slow tools.
    """
    present = detect()
    out: list[Tool] = []
    for tid, tool in TOOLS.items():
        if not present.get(tid):
            continue
        if tool.executes_code and not allow_code_execution:
            continue
        if tool.slow and not allow_slow:
            continue
        out.append(tool)
    return out


def missing_report(requested: list[str] | None = None) -> list[dict]:
    """
    For the requested tool ids (or all), report which are missing plus install hints so the
    manager can surface reduced-recall caveats honestly in the report's `scope.tools_missing`.
    """
    present = detect()
    ids = requested or list(TOOLS.keys())
    return [
        {"id": tid, "kind": TOOLS[tid].kind, "install": TOOLS[tid].install}
        for tid in ids
        if tid in TOOLS and not present.get(tid)
    ]


if __name__ == "__main__":
    import json

    present = detect()
    print(json.dumps({
        "available": [t for t, ok in present.items() if ok],
        "missing": missing_report(),
    }, indent=2))
