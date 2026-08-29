"""Conservative secret-pattern scanner for bounded code previews."""

from __future__ import annotations

import re


GENERIC_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(secret|token|access[_-]?token|client[_-]?secret|credential|api[_-]?key|password)\b\s*[:=]\s*['\"]?(?P<value>[^'\"\s]{8,})")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("supabase_jwt_or_key", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b")),
    ("database_url", re.compile(r"(?i)\b(postgres|postgresql|mysql|mongodb|redis)://[^\s'\"]+")),
    ("generic_secret_assignment", GENERIC_SECRET_ASSIGNMENT),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
)

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)


def scan_preview_for_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if label == "generic_secret_assignment":
            values = [match.group("value").strip("'\"").lower() for match in pattern.finditer(text)]
            real_values = [
                value
                for value in values
                if value not in {"replace_me", "replace-me", "changeme", "change_me", "example_value", "placeholder"}
                and not value.startswith(("your_", "your-", "<", "${"))
                and set(value) not in ({"x"}, {"*"})
            ]
            if real_values:
                findings.append(label)
        elif pattern.search(text):
            findings.append(label)
    return findings


def redact_secret_lines(text: str) -> str:
    text = PRIVATE_KEY_BLOCK.sub("[redacted possible private key block]", text)
    redacted_lines: list[str] = []
    for line in text.splitlines():
        if scan_preview_for_secrets(line):
            redacted_lines.append("[redacted possible secret line]")
        else:
            redacted_lines.append(line)
    if text.endswith("\n"):
        return "\n".join(redacted_lines) + "\n"
    return "\n".join(redacted_lines)


__all__ = ("GENERIC_SECRET_ASSIGNMENT", "PRIVATE_KEY_BLOCK", "SECRET_PATTERNS", "redact_secret_lines", "scan_preview_for_secrets")
