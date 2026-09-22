from __future__ import annotations

import os
from types import SimpleNamespace
from pathlib import Path

import pytest

import app.api.scientificforge_source_service as source_service

from app.api.file_ingest_service import attach_file
from app.api.scientificforge_source_service import (
    ScientificSourceError,
    resolve_attached_scientific_source,
    resolve_owned_attached_scientific_source,
)
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
)
from app.api.schemas.scientificforge import (
    ScientificExecutionRequest,
    ScientificOperation,
)


def _attach_csv(
    tmp_path: Path,
):
    source = tmp_path / "source.csv"

    source.write_text(
        "site,value\n"
        "A,1\n"
        "B,2\n"
        "C,3\n",
        encoding="utf-8",
    )

    ingest = tmp_path / "ingest"

    result = attach_file(
        source,
        ingest_root=ingest,
    )

    assert result.ready is True
    assert result.file is not None

    return (
        source,
        ingest,
        result,
    )


def test_scientificforge_execution_vocabulary_is_registered():
    assert (
        ExecutionToolKind.SCIENTIFIC_FORGE.value
        == "scientific_forge"
    )

    assert (
        ExecutionStatus.CANCELLED.value
        == "cancelled"
    )


def test_scientific_request_is_typed_and_bounded():
    request = ScientificExecutionRequest(
        operation=ScientificOperation.DESCRIPTIVE_STATS,
        source_file_id="file_0123456789abcdef",
        columns=["value"],
    )

    assert (
        request.operation
        == ScientificOperation.DESCRIPTIVE_STATS
    )

    assert request.columns == ["value"]


def test_resolves_verified_private_ingest_copy(
    tmp_path,
):
    source, ingest, result = _attach_csv(
        tmp_path
    )

    verified = (
        resolve_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )
    )

    assert verified.file_id == result.file_id
    assert verified.display_name == "source.csv"
    assert verified.file_kind == "csv"

    assert (
        verified.sha256
        == result.file.sha256
    )

    assert (
        verified.size_bytes
        == source.stat().st_size
    )

    assert (
        verified.source_path
        != source
    )

    assert (
        verified.source_path
        == (
            ingest
            / "raw"
            / result.file_id
            / "source.csv"
        ).resolve()
    )


def test_rejects_source_digest_change_after_ingest(
    tmp_path,
):
    _, ingest, result = _attach_csv(
        tmp_path
    )

    raw = (
        ingest
        / "raw"
        / result.file_id
        / "source.csv"
    )

    raw.write_text(
        "site,value\nA,999\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_.*changed_after_ingest",
    ):
        resolve_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )


def test_rejects_symlink_substitution(
    tmp_path,
):
    source, ingest, result = _attach_csv(
        tmp_path
    )

    raw = (
        ingest
        / "raw"
        / result.file_id
        / "source.csv"
    )

    raw.unlink()
    raw.symlink_to(source)

    with pytest.raises(
        ScientificSourceError,
        match="source_symlink_not_allowed",
    ):
        resolve_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )


def test_rejects_hardlink_substitution(
    tmp_path,
):
    source, ingest, result = _attach_csv(
        tmp_path
    )

    raw = (
        ingest
        / "raw"
        / result.file_id
        / "source.csv"
    )

    raw.unlink()
    os.link(
        source,
        raw,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_hardlink_not_allowed",
    ):
        resolve_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )


def test_rejects_untrusted_file_id_shape(
    tmp_path,
):
    with pytest.raises(
        ScientificSourceError,
        match="invalid_source_file_id",
    ):
        resolve_attached_scientific_source(
            "../../etc/passwd",
            ingest_root=tmp_path,
        )


def test_unknown_attached_file_id_fails_closed(
    tmp_path,
):
    with pytest.raises(
        ScientificSourceError,
        match="source_ingest_record_not_found",
    ):
        resolve_attached_scientific_source(
            "file_0123456789abcdef",
            ingest_root=tmp_path / "ingest",
        )


def test_source_verification_honors_cancellation(
    tmp_path,
):
    _, ingest, result = _attach_csv(
        tmp_path
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_verification_cancelled",
    ):
        resolve_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
            cancel_check=lambda: True,
        )


def _attach_scoped_csv(
    tmp_path: Path,
    *,
    project_id: str | None = None,
    conversation_id: str | None = None,
):
    source = tmp_path / "owned-source.csv"

    source.write_text(
        "site,value\n"
        "A,10\n"
        "B,20\n",
        encoding="utf-8",
    )

    ingest = tmp_path / "owned-ingest"

    result = attach_file(
        source,
        ingest_root=ingest,
        project_id=project_id,
        conversation_id=conversation_id,
    )

    assert result.ready is True
    assert result.file is not None

    return ingest, result


def test_owned_scientific_source_requires_authenticated_owner(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        project_id="project-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: None,
    )

    called = False

    def forbidden_low_level(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "low-level source bytes must not be touched"
        )

    monkeypatch.setattr(
        source_service,
        "resolve_attached_scientific_source",
        forbidden_low_level,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_owner_authentication_required",
    ):
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )

    assert called is False


def test_owned_scientific_source_rejects_unscoped_attachment_before_bytes(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    called = False

    def forbidden_low_level(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "unscoped source bytes must not be touched"
        )

    monkeypatch.setattr(
        source_service,
        "resolve_attached_scientific_source",
        forbidden_low_level,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_owner_context_required",
    ):
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )

    assert called is False


def test_owned_scientific_source_accepts_owned_project_scope(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        project_id="project-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "get_project_metadata",
        lambda project_id: {
            "project_id": project_id,
            "owner_user_id": "owner-alpha",
        },
    )

    verified = (
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )
    )

    assert verified.file_id == result.file_id


def test_owned_scientific_source_rejects_cross_account_project_before_bytes(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        project_id="project-beta",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "get_project_metadata",
        lambda project_id: {
            "project_id": project_id,
            "owner_user_id": "owner-beta",
        },
    )

    called = False

    def forbidden_low_level(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "cross-account source bytes must not be touched"
        )

    monkeypatch.setattr(
        source_service,
        "resolve_attached_scientific_source",
        forbidden_low_level,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_owner_context_mismatch",
    ):
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )

    assert called is False


def test_owned_scientific_source_accepts_owned_conversation_scope(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        conversation_id="conversation-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "get_conversation_metadata",
        lambda conversation_id: SimpleNamespace(
            conversation_id=conversation_id,
            owner_user_id="owner-alpha",
            project_id=None,
        ),
    )

    verified = (
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )
    )

    assert verified.file_id == result.file_id


def test_owned_scientific_source_rejects_contradictory_project_conversation_scope_before_bytes(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        project_id="project-alpha",
        conversation_id="conversation-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "get_project_metadata",
        lambda project_id: {
            "project_id": project_id,
            "owner_user_id": "owner-alpha",
        },
    )

    monkeypatch.setattr(
        source_service,
        "get_conversation_metadata",
        lambda conversation_id: SimpleNamespace(
            conversation_id=conversation_id,
            owner_user_id="owner-alpha",
            project_id="project-other",
        ),
    )

    called = False

    def forbidden_low_level(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "contradictory source bytes must not be touched"
        )

    monkeypatch.setattr(
        source_service,
        "resolve_attached_scientific_source",
        forbidden_low_level,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_scope_relationship_mismatch",
    ):
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )

    assert called is False


def test_owned_conversation_linked_project_must_also_belong_to_owner(
    tmp_path,
    monkeypatch,
):
    ingest, result = _attach_scoped_csv(
        tmp_path,
        conversation_id="conversation-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "current_user_id",
        lambda: "owner-alpha",
    )

    monkeypatch.setattr(
        source_service,
        "get_conversation_metadata",
        lambda conversation_id: SimpleNamespace(
            conversation_id=conversation_id,
            owner_user_id="owner-alpha",
            project_id="project-beta",
        ),
    )

    monkeypatch.setattr(
        source_service,
        "get_project_metadata",
        lambda project_id: {
            "project_id": project_id,
            "owner_user_id": "owner-beta",
        },
    )

    called = False

    def forbidden_low_level(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "cross-account linked-project bytes must not be touched"
        )

    monkeypatch.setattr(
        source_service,
        "resolve_attached_scientific_source",
        forbidden_low_level,
    )

    with pytest.raises(
        ScientificSourceError,
        match="source_owner_context_mismatch",
    ):
        resolve_owned_attached_scientific_source(
            result.file_id,
            ingest_root=ingest,
        )

    assert called is False
