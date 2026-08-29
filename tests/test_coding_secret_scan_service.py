from __future__ import annotations

from app.api.coding_secret_scan_service import redact_secret_lines, scan_preview_for_secrets


def test_secret_scan_detects_and_redacts_secret_like_lines():
    text = "safe = True\napi_key = 'abcdef1234567890'\n"

    findings = scan_preview_for_secrets(text)
    redacted = redact_secret_lines(text)

    assert "generic_secret_assignment" in findings
    assert "abcdef1234567890" not in redacted
    assert "[redacted possible secret line]" in redacted


def test_private_key_redaction_removes_the_entire_multiline_block():
    text = "before\n-----BEGIN PRIVATE KEY-----\nAAAABBBBCCCC\nDDDDEEEEFFFF\n-----END PRIVATE KEY-----\nafter\n"

    redacted = redact_secret_lines(text)

    assert "AAAABBBBCCCC" not in redacted
    assert "DDDDEEEEFFFF" not in redacted
    assert "[redacted possible private key block]" in redacted
    assert redacted.startswith("before\n")
    assert redacted.endswith("after\n")
