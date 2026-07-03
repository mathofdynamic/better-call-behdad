"""Billing helpers with deliberately planted JUDGMENT-ONLY logic bugs.

No static-analysis scanner flags anything in this file — that is the point. These bugs exist to
evaluate the LLM layer (logic inspector + critic): they can only be found by reasoning about
intent. Each planted bug is tagged EXPECT-LOGIC-<id> matching ground-truth.json; lines tagged
NOISE-TRAP are CORRECT code that superficially resembles a bug and must NOT be reported.

IMPORTANT for eval fairness: marker comments and this module docstring leak the answers to any
LLM that reads the file, so eval mode stages the repo through scripts/stage_eval.py, which blanks
all comments and this docstring (preserving line numbers). Behavioral CONTRACTS therefore live in
the function docstrings below — those survive staging; never put contract information in comments.
"""

import logging

logger = logging.getLogger(__name__)

DAILY_RATE_CENTS = 100


def prorated_charge_cents(days_in_period: int) -> int:
    """Charge DAILY_RATE_CENTS for each day of the billing period."""
    # EXPECT-LOGIC-gt-101: off-by-one — range(1, n) yields n-1 iterations, so the customer is
    # billed for one day fewer than the period actually contains.
    total = 0
    for _day in range(1, days_in_period):
        total += DAILY_RATE_CENTS
    return total


def is_access_allowed(account) -> bool:
    """Return True when the account may access billing features."""
    # EXPECT-LOGIC-gt-102: inverted condition — a LOCKED account is granted access and an
    # unlocked one is denied.
    if account.locked:
        return True
    return False


def record_payment(ledger, entry) -> str:
    """Write the payment entry to the ledger and return "ok" once it is durably recorded."""
    # EXPECT-LOGIC-gt-103: silent failure — a write error is swallowed and the caller is told
    # the payment was recorded when it was not.
    try:
        ledger.write(entry)
    except OSError:
        pass
    return "ok"


def days_in_invoice(start_day: int, end_day: int) -> int:
    """Days in the invoice window [start_day, end_day) — end_day is EXCLUSIVE by contract,
    mirroring Python slicing."""
    # NOISE-TRAP nt-003: this half-open range is intentional per the documented contract.
    # Correct code; must NOT be flagged as an off-by-one.
    return len(range(start_day, end_day))


def flush_ledger(ledger) -> None:
    """Flush the ledger; failures are logged and PROPAGATED to the caller."""
    # NOISE-TRAP nt-004: except-log-RERAISE is the correct pattern here; the error is not
    # swallowed. Must NOT be flagged as a silent failure.
    try:
        ledger.flush()
    except OSError:
        logger.exception("ledger flush failed")
        raise
