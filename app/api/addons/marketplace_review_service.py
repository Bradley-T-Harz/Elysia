"""Non-uploading Marketplace submission and admin-review contract previews."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api.addons.manifest_validator import load_permission_vocabulary
from app.api.addons.types import sanitize_public_text
from app.api.project_paths import config_path
from app.api.schemas.addons import MarketplaceReviewPreviewRequest, MarketplaceSubmissionPreviewRequest


UPLOAD_PRIVACY_NOTICE = (
    "The files you select will leave your computer and be transferred to Elysia Ecobotics / "
    "EcoSyneva Commons review infrastructure for validation and admin review. Remove secrets, "
    "credentials, private data, and material you cannot distribute before continuing."
)
ADMIN_REVIEW_DISCLAIMER = "Admin-reviewed means reviewed under the current process, not guaranteed safe."
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def prepare_submission_preview(request: MarketplaceSubmissionPreviewRequest) -> dict[str, Any]:
    known = set(load_permission_vocabulary().get("permissions", {}))
    unknown = sorted(set(request.requested_permissions) - known)
    blockers: list[str] = []
    if not _SHA256_RE.fullmatch(request.package_hash):
        blockers.append("package_hash_invalid")
    if unknown:
        blockers.append("unknown_permissions")
    if not request.static_scan_passed:
        blockers.append("static_scan_required")
    if not request.privacy_notice_acknowledged:
        blockers.append("upload_privacy_acknowledgement_required")
    ready = not blockers
    return {
        "preview_state": "ready_for_explicit_external_submission" if ready else "blocked",
        "proposed_marketplace_state": "pending_review" if ready else None,
        "addon_id": sanitize_public_text(request.addon_id),
        "version": request.version,
        "package_hash": request.package_hash,
        "publisher_identity": sanitize_public_text(request.publisher_identity),
        "source_kind": request.source_kind,
        "file_count": request.file_count,
        "total_size_bytes": request.total_size_bytes,
        "dependency_count": request.dependency_count,
        "requested_permissions": sorted(set(request.requested_permissions)),
        "blockers": blockers,
        "unknown_permissions": unknown,
        "privacy_notice": UPLOAD_PRIVACY_NOTICE,
        "privacy_notice_acknowledged": request.privacy_notice_acknowledged,
        "website_upload_is_local_only": False,
        "will_upload": False,
        "will_submit": False,
        "will_publish": False,
        "admin_approval_required": True,
        "ordinary_intake_executes_code": False,
        "git_url_fetch_allowed": False,
        "raw_paths_exposed": False,
    }


def prepare_admin_review_preview(request: MarketplaceReviewPreviewRequest) -> dict[str, Any]:
    blockers: list[str] = []
    known_permissions = set(load_permission_vocabulary().get("permissions", {}))
    unknown_permissions = sorted(set(request.requested_permissions) - known_permissions)
    if not _SHA256_RE.fullmatch(request.package_hash):
        blockers.append("package_hash_invalid")
    if not request.permission_review_complete:
        blockers.append("permission_review_incomplete")
    if not request.compatibility_review_complete:
        blockers.append("compatibility_review_incomplete")
    if not request.dependency_review_complete:
        blockers.append("dependency_review_incomplete")
    if not request.license_provenance_review_complete:
        blockers.append("license_provenance_review_incomplete")
    if not request.static_scan_passed:
        blockers.append("static_scan_failed_or_missing")
    if unknown_permissions:
        blockers.append("unknown_permissions")
    if request.decision == "approved" and blockers:
        review_state = "blocked"
        effective_decision = "no_decision_recorded"
    else:
        review_state = "review_contract_valid"
        effective_decision = request.decision
    return {
        "review_state": review_state,
        "marketplace_state_if_recorded": effective_decision,
        "addon_id": sanitize_public_text(request.addon_id),
        "version": request.version,
        "package_hash": request.package_hash,
        "publisher_identity": sanitize_public_text(request.publisher_identity),
        "requested_permissions": sorted(set(request.requested_permissions)),
        "unknown_permissions": unknown_permissions,
        "dependency_count": request.dependency_count,
        "reviewer": sanitize_public_text(request.reviewer),
        "review_timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "permission_review_complete": request.permission_review_complete,
        "compatibility_review_complete": request.compatibility_review_complete,
        "dependency_review_complete": request.dependency_review_complete,
        "license_provenance_review_complete": request.license_provenance_review_complete,
        "static_scan_passed": request.static_scan_passed,
        "known_risks": [sanitize_public_text(item) for item in request.known_risks],
        "sandbox_result": request.sandbox_result,
        "test_environment_label": sanitize_public_text(request.test_environment_label),
        "blockers": blockers,
        "disclaimer": ADMIN_REVIEW_DISCLAIMER,
        "exact_hash_binding": True,
        "new_hash_requires_new_review": True,
        "will_persist_review": False,
        "will_publish": False,
        "will_install": False,
        "will_execute": False,
        "raw_paths_exposed": False,
    }


def load_official_candidates() -> list[dict[str, Any]]:
    path = config_path("addons", "official_candidates.json")
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    safe: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        safe.append(
            {
                "addon_id": str(candidate.get("addon_id", "")),
                "name": str(candidate.get("name", "")),
                "publisher": str(candidate.get("publisher", "")),
                "version_channel": str(candidate.get("version_channel", "")),
                "version": str(candidate.get("version", "")),
                "extension_id": str(candidate.get("extension_id", "")),
                "coding_contract_version": str(candidate.get("coding_contract_version", "")),
                "listing_state": str(candidate.get("listing_state", "draft")),
                "required_profile": str(candidate.get("required_profile", "developer")),
                "purpose": str(candidate.get("purpose", "")),
                "requested_permissions": [str(item) for item in candidate.get("requested_permissions", [])],
                "install_action_live": bool(candidate.get("install_action_live", False)),
                "public_distribution_supported": bool(candidate.get("public_distribution_supported", False)),
                "canonical_marketplace_url": candidate.get("canonical_marketplace_url"),
                "live_availability_source": candidate.get("live_availability_source"),
                "in_app_install_control_live": bool(candidate.get("in_app_install_control_live", False)),
                "silent_shell_allowed": False,
                "silent_push_allowed": False,
                "silent_publish_allowed": False,
                "admin_reviewed": bool(candidate.get("admin_reviewed", False)),
                "raw_paths_exposed": False,
            }
        )
    return safe


__all__ = (
    "ADMIN_REVIEW_DISCLAIMER",
    "UPLOAD_PRIVACY_NOTICE",
    "load_official_candidates",
    "prepare_admin_review_preview",
    "prepare_submission_preview",
)
