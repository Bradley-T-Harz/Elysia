from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .config import SearxngWorkerConfig


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
_HOME_ADDRESS_RE = re.compile(r"\b\d{2,6}\s+[A-Za-z0-9 .'-]+\s+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd)\b", re.IGNORECASE)
_LONG_PRIVATE_TEXT_THRESHOLD = 700

_SECRET_PATTERNS = (
    "api key",
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "begin private key",
    "private key",
    "id_rsa",
    "id_ed25519",
    ".env",
)

_PRIVATE_PATH_PATTERNS = (
    "/home/",
    "~/",
    "~/.ssh",
    "vault/",
    "memory/journal/",
    "memory/chroma/",
    "data/conversations/",
    "data/file_ingest/",
)

_SENSITIVE_PATTERNS = {
    "legal_strategy": ("legal strategy", "lawsuit strategy", "defense strategy"),
    "medical_personal": ("my diagnosis", "my medical", "patient record", "medical record"),
    "financial_personal": ("my taxes", "my bank", "credit score", "financial account"),
    "activism_or_organizing_strategy": ("organizing strategy", "activism strategy", "protest plan"),
    "private_person_investigation": ("background check", "find personal info", "private person"),
    "security_vulnerability": ("zero day", "exploit", "vulnerability", "bypass authentication"),
    "business_strategy": ("business strategy", "stealth startup", "acquisition target"),
}


@dataclass
class QueryGuardResult:
    """Deterministic query safety decision before public search."""

    allowed: bool
    approval_required: bool = False
    sanitized_queries: list[str] = field(default_factory=list)
    queries_requested: list[str] = field(default_factory=list)
    queries_sent: list[str] = field(default_factory=list)
    query_hashes: list[str] = field(default_factory=list)
    blocked_query_preview: str = ""
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sensitive_categories: list[str] = field(default_factory=list)
    request_hash: str = ""
    sealed_egress_denied: bool = False


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").split())


def _hash_query(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def _redact_preview(text: str) -> str:
    preview = _normalize_query(text)[:180]
    preview = _EMAIL_RE.sub("[redacted-email]", preview)
    preview = _PHONE_RE.sub("[redacted-phone]", preview)
    preview = _HOME_ADDRESS_RE.sub("[redacted-address]", preview)
    preview = re.sub(
        r"(?:/home/[^\s]+|~/[^\s]+|[A-Za-z]:\\[^\s]+)",
        "[redacted-local-path]",
        preview,
    )
    for pattern in _SECRET_PATTERNS + _PRIVATE_PATH_PATTERNS:
        preview = re.sub(re.escape(pattern), "[redacted]", preview, flags=re.IGNORECASE)
    return preview


def _contains_blocked_content(query: str, config: SearxngWorkerConfig) -> list[str]:
    lowered = query.lower()
    reasons: list[str] = []

    for fragment in config.blocked_query_fragments:
        needle = str(fragment or "").lower().strip()
        if needle and needle in lowered:
            reasons.append("Query contains blocked private, credential, or local-path content.")
            break

    if any(pattern in lowered for pattern in _SECRET_PATTERNS):
        reasons.append("Query appears to contain credentials, secrets, tokens, or keys.")

    if any(pattern in lowered for pattern in _PRIVATE_PATH_PATTERNS):
        reasons.append("Query appears to contain private local paths or memory references.")

    if len(query) > _LONG_PRIVATE_TEXT_THRESHOLD and "\n" in query:
        reasons.append("Query appears to contain a large pasted private text block.")

    return reasons


def _sensitive_categories(query: str) -> list[str]:
    lowered = query.lower()
    categories: list[str] = []
    for category, patterns in _SENSITIVE_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            categories.append(category)
    if _EMAIL_RE.search(query):
        categories.append("email_address")
    if _PHONE_RE.search(query):
        categories.append("phone_number")
    if _HOME_ADDRESS_RE.search(query):
        categories.append("home_address")
    return sorted(set(categories))


def guard_public_queries(
    queries: list[str],
    *,
    config: SearxngWorkerConfig,
    approval_token: str | None = None,
    exact_approval_validated: bool = False,
) -> QueryGuardResult:
    """
    Decide whether proposed public query text is safe to send outward.

    This is lexical and local only. It does not read files, memory, vaults, call
    models, call workers, or touch the network.
    """
    # Kept in the signature for compatibility, but arbitrary token strings are
    # never treated as authorization. The service passes only a validated fact.
    del approval_token
    requested = [_normalize_query(query) for query in list(queries or [])]
    normalized = [query for query in requested if query]
    refusal_reasons: list[str] = []
    warnings: list[str] = []

    max_queries = int(config.limits.get("max_queries_per_ticket") or 3)
    max_query_length = int(config.limits.get("max_query_length") or 300)
    max_total_length = int(config.limits.get("max_total_query_length") or 900)

    if not normalized:
        refusal_reasons.append("At least one non-empty public query is required.")

    if len(normalized) > max_queries:
        refusal_reasons.append(f"Query count exceeds configured limit of {max_queries}.")

    if sum(len(query) for query in normalized) > max_total_length:
        refusal_reasons.append("Total query length exceeds configured limit.")

    for query in normalized:
        if len(query) > max_query_length:
            refusal_reasons.append(
                f"Query exceeds configured length limit of {max_query_length} characters."
            )
        refusal_reasons.extend(_contains_blocked_content(query, config))

    query_hashes = [_hash_query(query) for query in normalized]
    blocked_preview = _redact_preview(" ".join(normalized))

    request_hash = _hash_query("\n".join(normalized)) if normalized else ""
    sealed_denied = any(
        marker in " ".join(normalized).casefold()
        for marker in ("sealed memory", "sealed-memory", "sealed vault", "sealed content")
    )
    if sealed_denied:
        refusal_reasons.append("Sealed content is categorically denied from research egress.")

    if refusal_reasons:
        return QueryGuardResult(
            allowed=False,
            approval_required=False,
            sanitized_queries=[],
            queries_requested=requested,
            queries_sent=[],
            query_hashes=query_hashes,
            blocked_query_preview=blocked_preview,
            refusal_reasons=sorted(set(refusal_reasons)),
            warnings=warnings,
            request_hash=request_hash,
            sealed_egress_denied=sealed_denied,
        )

    sensitive = sorted({category for query in normalized for category in _sensitive_categories(query)})
    if sensitive and not exact_approval_validated:
        return QueryGuardResult(
            allowed=False,
            approval_required=True,
            sanitized_queries=[],
            queries_requested=requested,
            queries_sent=[],
            query_hashes=query_hashes,
            blocked_query_preview=blocked_preview,
            refusal_reasons=[
                "Sensitive public-web research query requires approval before network use.",
            ],
            warnings=[f"Sensitive query categories detected: {', '.join(sensitive)}."],
            sensitive_categories=sensitive,
            request_hash=request_hash,
        )

    if sensitive:
        warnings.append(f"Sensitive query categories exactly approved: {', '.join(sensitive)}.")

    return QueryGuardResult(
        allowed=True,
        approval_required=False,
        sanitized_queries=normalized,
        queries_requested=requested,
        queries_sent=normalized,
        query_hashes=query_hashes,
        blocked_query_preview="",
        refusal_reasons=[],
        warnings=warnings,
        sensitive_categories=sensitive,
        request_hash=request_hash,
    )


__all__ = ("QueryGuardResult", "guard_public_queries")
