"""
stage_eval.py — stage the seeded repo for an honest LLM-layer evaluation.

The fixture files carry EXPECT-*/NOISE-TRAP marker comments and a self-describing module
docstring so maintainers (and the deterministic harness) know what is planted where. Scanners
ignore comments — but LLM inspectors READ them, which would leak the answers and invalidate the
eval. This script copies the fixture and blanks every full-line comment and each module
docstring, replacing each with a bare "#" so LINE NUMBERS ARE PRESERVED (ground-truth.json
matches by line). Function docstrings are KEPT: they are the behavioral contracts the logic
inspector judges against. ground-truth.json itself is never copied.

  python scripts/stage_eval.py <fixture-dir> <dest-dir>

Stdlib only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

EXCLUDE = {"ground-truth.json"}


def neutralize_python(text: str) -> str:
    """Blank the module docstring and all full-line comments, preserving line count."""
    lines = text.split("\n")
    out: list[str] = []
    in_module_doc = False
    module_doc_done = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not module_doc_done and not in_module_doc:
            if stripped.startswith(('"""', "'''")):
                quote = stripped[:3]
                in_module_doc = not (stripped.endswith(quote) and len(stripped) >= 6)
                module_doc_done = not in_module_doc
                out.append("#")
                continue
            if stripped and not stripped.startswith("#"):
                module_doc_done = True  # first real statement: no module docstring
        elif in_module_doc:
            out.append("#")
            if stripped.endswith(('"""', "'''")):
                in_module_doc = False
                module_doc_done = True
            continue
        if stripped.startswith("#"):
            out.append("#")
        else:
            out.append(line)
    return "\n".join(out)


def neutralize_js(text: str) -> str:
    """Blank full-line // comments (the fixture's marker convention), preserving line count."""
    out = []
    for line in text.split("\n"):
        out.append("//" if line.strip().startswith("//") else line)
    return "\n".join(out)


def stage(src: Path, dst: Path) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    count = 0
    for p in src.rglob("*"):
        if p.is_dir() or p.name in EXCLUDE:
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix == ".py":
            target.write_text(neutralize_python(p.read_text(encoding="utf-8")),
                              encoding="utf-8", newline="\n")
        elif p.suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            target.write_text(neutralize_js(p.read_text(encoding="utf-8")),
                              encoding="utf-8", newline="\n")
        else:
            shutil.copy2(p, target)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stage the seeded repo for LLM-layer eval")
    ap.add_argument("fixture", help="path to tests/fixtures/seeded-repo")
    ap.add_argument("dest", help="destination directory (scratch space)")
    args = ap.parse_args(argv)
    src, dst = Path(args.fixture), Path(args.dest)
    if not (src / "ground-truth.json").exists():
        print(f"ERROR: {src} does not look like the seeded fixture (no ground-truth.json)",
              file=sys.stderr)
        return 1
    n = stage(src, dst)
    print(f"staged {n} files to {dst} (markers blanked, line numbers preserved, "
          "ground-truth.json excluded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
