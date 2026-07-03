"""
test_gate.py — decision-table tests for the PreToolUse fix gate (platform/claude/hooks/gate.py).

Every historical bypass gets a pinned regression case:
  * substring-allowlist hole      ("rm -rf src # reports/")
  * ungated PowerShell tool       (Remove-Item / Set-Content)
  * interpreter-driven writes     (python -c, node -e, here-doc redirects)

Run standalone (python tests/eval/test_gate.py) or via tests/eval/run_eval.py, which imports
run_cases(). Stdlib only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform" / "claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))

import gate  # noqa: E402

ACTIVE = {"BEHDAD_ACTIVE": "1"}
APPROVED = {"BEHDAD_ACTIVE": "1", "BEHDAD_APPROVED": "1"}
INACTIVE: dict[str, str] = {}


def _bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "."}


def _ps(cmd: str) -> dict:
    return {"tool_name": "PowerShell", "tool_input": {"command": cmd}, "cwd": "."}


def _write(path: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": "."}


# (name, event, env, expect_allow)
CASES: list[tuple[str, dict, dict, bool]] = [
    # --- regression: BUG 1 — allowlist substring applied to the whole command -------------
    ("bug1: rm with allowed word in comment", _bash("rm -rf src # reports/"), ACTIVE, False),
    ("bug1: rm via path traversal", _bash("rm -rf reports/../src"), ACTIVE, False),
    ("bug1: write via traversal path", _write("reports/../src/app.py"), ACTIVE, False),
    # --- regression: BUG 2 — PowerShell was never inspected -------------------------------
    ("bug2: PS Remove-Item", _ps("Remove-Item -Recurse -Force src"), ACTIVE, False),
    ("bug2: PS Set-Content", _ps("Set-Content app.py 'pwned'"), ACTIVE, False),
    ("bug2: PS Out-File via pipe", _ps("'x' | Out-File app.py"), ACTIVE, False),
    ("bug2: PS Invoke-Expression", _ps("iex (Get-Content x.ps1 -Raw)"), ACTIVE, False),
    ("bug2: PS call operator", _ps("& C:/evil.exe"), ACTIVE, False),
    # --- regression: BUG 3 — interpreter-driven writes ------------------------------------
    ("bug3: python -c write", _bash("python -c \"open('a','w').write('x')\""), ACTIVE, False),
    ("bug3: python -m", _bash("python -m pip install requests"), ACTIVE, False),
    ("bug3: node -e", _bash("node -e \"require('fs').writeFileSync('a','x')\""), ACTIVE, False),
    ("bug3: here-doc redirect", _bash("cat <<EOF > app.py\npwned\nEOF"), ACTIVE, False),
    ("bug3: command substitution", _bash("echo $(rm -rf src)"), ACTIVE, False),
    ("bug3: backticks", _bash("echo `rm -rf src`"), ACTIVE, False),
    # --- default-deny basics ---------------------------------------------------------------
    ("deny: unknown binary", _bash("make install"), ACTIVE, False),
    ("deny: pip install", _bash("pip install requests"), ACTIVE, False),
    ("deny: tee into source", _bash("echo x | tee app.py"), ACTIVE, False),
    ("deny: redirect into source", _bash("echo x > app.py"), ACTIVE, False),
    ("deny: git commit", _bash("git commit -m x"), ACTIVE, False),
    ("deny: git branch -D", _bash("git branch -D main"), ACTIVE, False),
    ("deny: mutation hidden mid-pipeline", _bash("ls && rm -rf src"), ACTIVE, False),
    ("deny: npx arbitrary package", _bash("npx cowsay hi"), ACTIVE, False),
    ("deny: remediate.py pre-approval", _bash("python scripts/remediate.py --patch p.diff"), ACTIVE, False),
    # --- legitimate audit workflow must pass ------------------------------------------------
    ("allow: git status", _bash("git status"), ACTIVE, True),
    ("allow: git log", _bash("git log --oneline -20"), ACTIVE, True),
    ("allow: git diff", _bash("git diff HEAD~1"), ACTIVE, True),
    ("allow: grep pipeline", _bash("grep -rn password src | head -50"), ACTIVE, True),
    ("allow: bandit scan", _bash("bandit -r . -f json"), ACTIVE, True),
    ("allow: semgrep scan", _bash("semgrep --config p/default --sarif ."), ACTIVE, True),
    ("allow: behdad scanner script", _bash("python /skill/scripts/run_scanners.py . --depth quick"), ACTIVE, True),
    ("allow: behdad aggregate script", _bash('python "C:/s k i l l/scripts/aggregate.py" in.json'), ACTIVE, True),
    ("allow: redirect into .behdad", _bash("python /skill/scripts/run_scanners.py . > .behdad/scan.json"), ACTIVE, True),
    ("allow: redirect to null", _bash("git log > /dev/null"), ACTIVE, True),
    ("allow: fd duplication", _bash("git status 2>&1"), ACTIVE, True),
    ("allow: PS read-only", _ps("Get-ChildItem -Recurse src"), ACTIVE, True),
    ("allow: PS Select-String", _ps("Select-String -Path app.py -Pattern secret"), ACTIVE, True),
    ("allow: copy fixture into scratchpad", _bash("cp -r tests/fixtures/seeded-repo /tmp/scratchpad/eval"), ACTIVE, True),
    ("deny: copy into source", _bash("cp evil.py src/app.py"), ACTIVE, False),
    # --- file tools ------------------------------------------------------------------------
    ("allow: Write into .behdad", _write(".behdad/state.json"), ACTIVE, True),
    ("allow: Write report", _write("reports/audit-2026.md"), ACTIVE, True),
    ("deny: Write into source", _write("src/app.py"), ACTIVE, False),
    ("deny: Edit into source",
     {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}, "cwd": "."}, ACTIVE, False),
    # --- gate state ------------------------------------------------------------------------
    ("inactive: everything allowed", _bash("rm -rf src"), INACTIVE, True),
    ("approved: mutation allowed", _bash("rm -rf src"), APPROVED, True),
    ("approved: remediate.py allowed", _bash("python scripts/remediate.py --patch p.diff"), APPROVED, True),
    ("ungated tool passes", {"tool_name": "Read", "tool_input": {"file_path": "src/app.py"}, "cwd": "."}, ACTIVE, True),
]


def run_cases() -> list[tuple[bool, str, str]]:
    """Return [(ok, name, detail)] for every table case plus the registry-sync check."""
    out: list[tuple[bool, str, str]] = []
    for name, event, env, expect_allow in CASES:
        allow, reason = gate.decide(event, env)
        ok = allow == expect_allow
        out.append((ok, f"gate: {name}", "" if ok else f"got allow={allow} ({reason})"))

    # Sync check: every scanner binary Behdad can invoke must be allowlisted in the gate.
    import tool_registry as reg
    binaries = {t.binary.lower() for t in reg.TOOLS.values()}
    missing = binaries - {s.lower() for s in gate.SCANNER_TOKENS}
    out.append((not missing, "gate: SCANNER_TOKENS covers tool_registry", str(sorted(missing))))
    return out


def run_subprocess_smoke() -> list[tuple[bool, str, str]]:
    """End-to-end: pipe JSON into gate.py as Claude Code would; assert exit codes 0/2."""
    gate_py = ROOT / "platform" / "claude" / "hooks" / "gate.py"
    smoke = [
        ("smoke: bypass payload exits 2", _bash("rm -rf src # reports/"), ACTIVE, 2),
        ("smoke: scanner exits 0", _bash("bandit -r . -f json"), ACTIVE, 0),
        ("smoke: inactive exits 0", _bash("rm -rf src"), INACTIVE, 0),
    ]
    out: list[tuple[bool, str, str]] = []
    for name, event, env, want in smoke:
        proc = subprocess.run(
            [sys.executable, str(gate_py)], input=json.dumps(event),
            capture_output=True, text=True, env={**_min_env(), **env}, timeout=30,
        )
        ok = proc.returncode == want
        out.append((ok, f"gate: {name}", "" if ok else f"exit {proc.returncode}, want {want}"))
    return out


def _min_env() -> dict[str, str]:
    import os
    return {k: v for k, v in os.environ.items() if k not in ("BEHDAD_ACTIVE", "BEHDAD_APPROVED")}


if __name__ == "__main__":
    rows = run_cases() + run_subprocess_smoke()
    width = max(len(n) for _, n, _ in rows)
    failed = 0
    for ok, name, detail in rows:
        if not ok:
            failed += 1
        print(f"  [{'OK' if ok else 'XX'}] {name.ljust(width)}  {('-- ' + detail) if detail else ''}")
    print(f"\n{len(rows) - failed}/{len(rows)} gate checks passed.")
    raise SystemExit(1 if failed else 0)
