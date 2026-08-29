from __future__ import annotations

from uuid import UUID

from app.ids import new_id, uuid7


def test_uuid7_is_rfc9562_unique_and_time_sortable():
    identifiers = [uuid7() for _ in range(512)]

    assert len(set(identifiers)) == len(identifiers)
    assert all(identifier.version == 7 for identifier in identifiers)
    assert all(identifier.variant == "specified in RFC 4122" for identifier in identifiers)
    assert identifiers == sorted(identifiers)


def test_prefixed_first_class_id_retains_full_uuid7():
    value = new_id("artifact")
    parsed = UUID(value.removeprefix("artifact_"))

    assert parsed.version == 7
    assert str(parsed) in value
