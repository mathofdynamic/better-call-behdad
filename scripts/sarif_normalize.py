"""
sarif_normalize.py — collapse N heterogeneous scanner outputs into one normalized stream.

SARIF v2.1.0 is the lingua franca, but not every tool emits it (bandit, ruff, eslint, gitleaks
and osv-scanner speak their own JSON). This module converts each into a common "raw finding"
dict aligned with schemas/finding.schema.json (status defaults to "candidate", ground_truth=true
since these are scanner-anchored). The LLM inspectors consume this normalized list rather than
re-parsing each tool. Stdlib only.

Each raw finding:
  { source, rule_id, canonical_ids[], severity, file, line, message, ground_truth: true }
Severity is mapped onto Behdad's bands: critical|high|medium|low|info.
"""

from __future__ import annotations

import re

_CWE_RE = re.compile(r"CWE[-_ ]?(\d+)", re.IGNORECASE)


def _cwes(*texts: str) -> list[str]:
    ids: list[str] = []
    for t in texts:
        if not t:
            continue
        for m in _CWE_RE.finditer(str(t)):
            cid = f"CWE-{int(m.group(1))}"
            if cid not in ids:
                ids.append(cid)
    return ids


def _band(value: str, mapping: dict[str, str], default: str = "medium") -> str:
    return mapping.get(str(value).lower(), default)


def _finding(source, rule_id, severity, file, line, message, canonical_ids=None) -> dict:
    return {
        "source": source,
        "rule_id": rule_id or "",
        "canonical_ids": canonical_ids or [],
        "severity": severity,
        "file": file or "",
        "line": int(line) if line else 0,
        "message": (message or "").strip(),
        "ground_truth": True,
        "status": "candidate",
    }


# --- SARIF v2.1.0 (semgrep, trivy, codeql) ------------------------------------------------

_SARIF_LEVEL = {"error": "high", "warning": "medium", "note": "low", "none": "info"}
# SARIF security-severity is a CVSS-like 0-10 string in properties; map to bands.
def _sarif_secsev(score: str | None) -> str | None:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s >= 9.0:
        return "critical"
    if s >= 7.0:
        return "high"
    if s >= 4.0:
        return "medium"
    if s > 0:
        return "low"
    return "info"


def from_sarif(doc: dict, source: str) -> list[dict]:
    out: list[dict] = []
    for run in doc.get("runs", []) or []:
        # Build a rule lookup for tags/CWEs/security-severity.
        rules: dict[str, dict] = {}
        driver = (run.get("tool") or {}).get("driver") or {}
        for r in driver.get("rules", []) or []:
            if r.get("id"):
                rules[r["id"]] = r
        for res in run.get("results", []) or []:
            rule_id = res.get("ruleId") or ""
            rule = rules.get(rule_id, {})
            props = {**(rule.get("properties") or {}), **(res.get("properties") or {})}
            # CWEs can live in rule tags, properties.cwe, or the message.
            tags = props.get("tags") or props.get("cwe") or []
            msg = ((res.get("message") or {}).get("text")) or ""
            canonical = _cwes(rule_id, msg, " ".join(map(str, tags)) if isinstance(tags, list) else str(tags))
            # Severity: prefer security-severity, then result.level, then rule default.
            sev = _sarif_secsev(props.get("security-severity"))
            if not sev:
                level = res.get("level") or (rule.get("defaultConfiguration") or {}).get("level") or "warning"
                sev = _SARIF_LEVEL.get(level, "medium")
            # Location.
            file, line = "", 0
            locs = res.get("locations") or []
            if locs:
                phys = (locs[0].get("physicalLocation") or {})
                file = ((phys.get("artifactLocation") or {}).get("uri")) or ""
                line = (phys.get("region") or {}).get("startLine") or 0
            out.append(_finding(source, rule_id, sev, file, line, msg, canonical))
    return out


# --- Bandit JSON --------------------------------------------------------------------------

_BANDIT_SEV = {"high": "high", "medium": "medium", "low": "low"}
def from_bandit(doc: dict, source: str = "bandit") -> list[dict]:
    out: list[dict] = []
    for r in doc.get("results", []) or []:
        # Bandit gives the CWE as a bare number in issue_cwe.id (e.g. 89), plus any CWE
        # mentioned in the message text.
        canonical: list[str] = []
        cwe_id = (r.get("issue_cwe") or {}).get("id")
        if cwe_id:
            canonical.append(f"CWE-{cwe_id}")
        for c in _cwes(r.get("issue_text", "")):
            if c not in canonical:
                canonical.append(c)
        out.append(_finding(
            source, r.get("test_id"),
            _band(r.get("issue_severity", "medium"), _BANDIT_SEV),
            r.get("filename"), r.get("line_number"),
            r.get("issue_text"), canonical,
        ))
    return out


# --- Ruff JSON ----------------------------------------------------------------------------

def from_ruff(doc: list, source: str = "ruff") -> list[dict]:
    # Ruff `--output-format json` emits a list of diagnostics. Lint findings are quality/info
    # by nature; security rules (flake8-bandit "S") get bumped.
    out: list[dict] = []
    for d in doc or []:
        code = d.get("code") or ""
        sev = "medium" if str(code).startswith("S") else "low"
        loc = d.get("location") or {}
        out.append(_finding(
            source, code, sev,
            d.get("filename"), loc.get("row"),
            d.get("message"), _cwes(code),
        ))
    return out


# --- ESLint JSON --------------------------------------------------------------------------

_ESLINT_SEV = {2: "medium", 1: "low"}
def from_eslint(doc: list, source: str = "eslint") -> list[dict]:
    out: list[dict] = []
    for file_result in doc or []:
        path = file_result.get("filePath") or ""
        for m in file_result.get("messages", []) or []:
            sev = _ESLINT_SEV.get(m.get("severity"), "low")
            # security plugins encode risk in ruleId (e.g. security/detect-*)
            if "security" in str(m.get("ruleId", "")):
                sev = "high"
            out.append(_finding(
                source, m.get("ruleId"), sev,
                path, m.get("line"), m.get("message"),
            ))
    return out


# --- Gitleaks JSON ------------------------------------------------------------------------

def from_gitleaks(doc: list, source: str = "gitleaks") -> list[dict]:
    # Every leak is a hardcoded-secret finding -> CWE-798, high severity.
    out: list[dict] = []
    for r in doc or []:
        desc = r.get("Description") or r.get("RuleID") or "Hardcoded secret detected"
        out.append(_finding(
            source, r.get("RuleID"), "high",
            r.get("File"), r.get("StartLine"),
            f"{desc} (secret: {r.get('RuleID', 'generic')})", ["CWE-798"],
        ))
    return out


# --- OSV-Scanner JSON ---------------------------------------------------------------------

_OSV_SEV = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low"}
def from_osv(doc: dict, source: str = "osv-scanner") -> list[dict]:
    out: list[dict] = []
    for res in doc.get("results", []) or []:
        src = (res.get("source") or {}).get("path", "")
        for pkg in res.get("packages", []) or []:
            name = (pkg.get("package") or {}).get("name", "")
            ver = (pkg.get("package") or {}).get("version", "")
            for v in pkg.get("vulnerabilities", []) or []:
                vid = v.get("id", "")
                # Severity from database_specific or CVSS; default high for known vulns.
                sev = "high"
                for s in (v.get("severity") or []):
                    band = _OSV_SEV.get(str(s.get("score", "")).upper())
                    if band:
                        sev = band
                aliases = v.get("aliases", []) or []
                out.append(_finding(
                    source, vid, sev,
                    src, 0,
                    f"{name}@{ver}: {v.get('summary', vid)} ({', '.join([vid, *aliases][:3])})",
                    _cwes(*(v.get("summary", ""), " ".join(aliases))),
                ))
    return out


# --- Dispatch -----------------------------------------------------------------------------

# Maps a scanner id to (parser, output_kind). run_scanners.py uses this to normalize.
PARSERS = {
    "semgrep": (from_sarif, "sarif"),
    "trivy": (from_sarif, "sarif"),
    "codeql": (from_sarif, "sarif"),
    "bandit": (from_bandit, "json"),
    "ruff": (from_ruff, "json"),
    "eslint": (from_eslint, "json"),
    "gitleaks": (from_gitleaks, "json"),
    "osv-scanner": (from_osv, "json"),
}


def normalize(tool_id: str, parsed_json) -> list[dict]:
    """Normalize one tool's already-parsed JSON document into raw findings."""
    if tool_id not in PARSERS:
        return []
    parser, _ = PARSERS[tool_id]
    try:
        if tool_id in ("semgrep", "trivy", "codeql"):
            return parser(parsed_json, tool_id)
        return parser(parsed_json)
    except Exception as exc:  # never let one malformed report crash the whole scan
        return [{
            "source": tool_id, "rule_id": "_parse_error", "canonical_ids": [],
            "severity": "info", "file": "", "line": 0,
            "message": f"Failed to normalize {tool_id} output: {exc}",
            "ground_truth": True, "status": "candidate",
        }]
