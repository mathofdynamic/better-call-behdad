"""Test file — Behdad must RELAX security/secret rules here.

NOISE-TRAP: the fake password below is expected in a test fixture and must NOT be
reported as a hardcoded-secret finding (config/fp-exclusions.yaml relaxed_in_tests).
"""

FAKE_TEST_PASSWORD = "password123"  # NOISE-TRAP: test fixture credential, not a real secret


def test_placeholder():
    assert FAKE_TEST_PASSWORD == "password123"
