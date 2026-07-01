"""A deliberately flawed sample app for exercising Behdad's scanners.

Each planted issue is tagged EXPECT-<CWE> so the eval harness can check it is found.
Lines tagged NOISE-TRAP are benign patterns that must NOT be reported (false-positive bait).
"""

import sqlite3
import subprocess
import hashlib

# EXPECT-CWE-798: hardcoded secret (bandit + gitleaks should flag)
API_KEY = "AKIA1234567890EXAMPLE"
DB_PASSWORD = "supersecret_prod_password_9f8a7b"


def get_user(conn: sqlite3.Connection, user_id: str):
    # EXPECT-CWE-89: SQL injection via string formatting (semgrep/bandit taint)
    query = "SELECT * FROM users WHERE id = '%s'" % user_id
    return conn.execute(query).fetchall()


def run_backup(path: str):
    # EXPECT-CWE-78: command injection via shell=True with interpolated input
    subprocess.call("tar czf backup.tgz " + path, shell=True)


def hash_password(pw: str) -> str:
    # EXPECT-CWE-327: weak hash for password storage
    return hashlib.md5(pw.encode()).hexdigest()


def evaluate(expr: str):
    # EXPECT-CWE-95: eval on user-controlled string
    return eval(expr)


def safe_total(items):
    # NOISE-TRAP: a plain sum in a small loop — perf inspector must NOT flag this.
    total = 0
    for it in items:
        total += it
    return total


def format_name(first: str, last: str) -> str:
    # NOISE-TRAP: string concatenation is not a security issue; must NOT be flagged.
    return first + " " + last
