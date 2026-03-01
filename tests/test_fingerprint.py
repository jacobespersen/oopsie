"""Unit tests for error fingerprinting."""

from oopsie.utils.fingerprint import compute_fingerprint


def test_same_inputs_same_fingerprint():
    """Same error_class, message, and stack_trace produce the same fingerprint."""
    fp1 = compute_fingerprint("NoMethodError", "undefined method 'foo'", "line1\nline2")
    fp2 = compute_fingerprint("NoMethodError", "undefined method 'foo'", "line1\nline2")
    assert fp1 == fp2
    assert len(fp1) <= 64


def test_different_message_different_fingerprint():
    """Different message produces different fingerprint."""
    fp1 = compute_fingerprint("NoMethodError", "message one", None)
    fp2 = compute_fingerprint("NoMethodError", "message two", None)
    assert fp1 != fp2


def test_different_stack_trace_different_fingerprint():
    """Different first line of stack_trace produces different fingerprint."""
    fp1 = compute_fingerprint("E", "m", "app/models/user.rb:42")
    fp2 = compute_fingerprint("E", "m", "app/controllers/other.rb:10")
    assert fp1 != fp2


def test_none_stack_trace_uses_empty_string():
    """stack_trace None is treated as empty first line."""
    fp_none = compute_fingerprint("E", "m", None)
    fp_empty = compute_fingerprint("E", "m", "")
    assert fp_none == fp_empty


def test_fingerprint_length():
    """Fingerprint fits in Error.fingerprint String(64)."""
    fp = compute_fingerprint("A" * 100, "B" * 100, "C" * 100)
    assert len(fp) <= 64
    assert len(fp) >= 16
