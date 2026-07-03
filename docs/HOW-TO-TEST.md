# Trying Behdad on a project

The whole point is that it's a **skill you just run**. No PATH setup, no scripts to operate.

## 1. Install (once)

```bash
git clone https://github.com/mathofdynamic/better-call-behdad.git
cd better-call-behdad
python platform/claude/install.py
```

Optional but recommended — install the scanners for full recall. Behdad **auto-discovers** them
even if they aren't on your PATH:

```bash
pip install ruff bandit semgrep
```

## 2. Run it

In a **new** Claude Code session:

```
/behdad this                     # audits the CURRENT directory
/behdad C:\path\to\your-project  # or point it at any path
```

`this`, `here`, `.`, or no argument all mean "audit the current working directory." You can also
just ask: *"audit this project with behdad."*

That's it. Behdad will:
1. scan your project with real tools,
2. run its inspector agents + the critic gate,
3. show you a **Full Diagnostic Report** and a **Prioritized Action Report**, and
4. **stop and ask** before changing anything.

## 3. Read how it did — it tells you itself

Every run ends with a **"How this audit performed"** section, computed automatically:

- **Noise control:** *"Scanners raised 43 raw findings; after verification Behdad reported 6
  (86% filtered as noise)."* — this is the whole value proposition, shown every time.
- **Coverage:** which languages/aspects were covered, and any missing scanners (honest reduced-recall note).
- **After fixes** (if you approve any): *"Resolved 5 findings, introduced 0 new ones, tests still green."*

No separate tool, no spreadsheets. If you approve fixes, they're applied on a snapshot, verified,
and **auto-rolled-back** if anything breaks.

## Before you let it fix things

Run it on a project that's **committed to git** (or backed up). Behdad only edits after you
approve and rolls back broken fixes automatically — but a clean git state is always the right
safety net before any tool touches your code.

---

### For maintainers: rigorous benchmarking (optional)

If you want hard precision/recall numbers (not needed for normal use):

- **`/behdad eval`** — runs the full pipeline (including the inspectors and critic) against the
  seeded repo and scores it automatically against an exhaustive ground truth: recall,
  **judgment_recall** (logic bugs no scanner sees), precision, noise-trap hits, critic kill rate.
- **`python tests/eval/run_eval.py [--strict]`** — the deterministic KPI scorecard (scanner
  normalization, aggregation, the fix gate's decision table, the scorer itself). `--strict`
  turns missing-scanner skips into failures for CI.
- **`tests/eval/measure.py`** — triage sheet + scoring for real-world (non-seeded) repos.
- **[`docs/BENCHMARK.md`](BENCHMARK.md)** — the blind-trial protocol and the running results table.
