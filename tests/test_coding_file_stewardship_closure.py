from __future__ import annotations

import difflib
from hashlib import sha256

from app.api.routes import coding_file_types, coding_files
from app.api.coding_file_operation_service import execute_file_operation, plan_file_operation
from app.api.coding_patch_service import apply_patch_with_approval, patch_hash_for_diff
from app.api.coding_patch_validation_service import validate_patch_targets
from app.api.main import create_app
from app.api.schemas.coding_file_operations import (
    CodingFileOperationExecuteRequest,
    CodingFileOperationPlanRequest,
)
from app.api.schemas.coding_patch import CodingPatchApplyRequest
from tests.coding_approval_test_helpers import approval_fields_for_plan
from tests.asgi_test_client import ASGITestClient


def _write_fixture_matrix(root):
    files = {
        "README.md": "# Read Me\n",
        "LICENSE": "Example license text\n",
        "CHANGELOG.md": "# Changelog\n",
        "Dockerfile": "FROM scratch\n",
        ".gitignore": "dist/\n",
        ".env": "TOKEN=real_secret_value\n",
        ".env.example": "TOKEN=replace_this_secret\nPUBLIC_URL=http://127.0.0.1\n",
        "package-lock.json": '{"lockfileVersion": 3, "packages": {}}\n',
        "Cargo.lock": "# generated\nversion = 3\n",
        "pyproject.toml": "[project]\nname = \"demo\"\n",
        "requirements.txt": "fastapi\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
        "vite.config.ts": "export default {}\n",
        "crlf.txt": "one\r\ntwo\r\n",
        "NO_EXTENSION": "plain text\n",
        "bidi.txt": "safe text \u202esecret-looking visual trick\n",
        "small.csv": "name,value\nalpha,1\n",
        "small.tsv": "name\tvalue\nalpha\t1\n",
        "malformed.json": '{"missing": ',
        "malformed.yaml": "items:\n  - ok\n  - : bad\n",
        "index.html": "<html><head><script>alert('x')</script></head><body>Hi</body></html>\n",
        "binary.bin": b"abc\x00def",
        "large.txt": "line\n" * 4000,
    }
    for name, content in files.items():
        path = root / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return files


def _client() -> ASGITestClient:
    return ASGITestClient(create_app())


async def _await_payload(coro):
    return await coro


def _diff(old: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def test_testclient_registers_file_stewardship_routes():
    client = _client()
    paths = set(client.app.openapi()["paths"])

    assert "/coding/file-types" in paths
    assert "/coding/file/inspect-type" in paths
    assert "/coding/file/read-preview" in paths


def test_file_type_registry_and_inspect_routes_cover_fixture_matrix(tmp_path):
    import asyncio

    _write_fixture_matrix(tmp_path)

    registry = asyncio.run(_await_payload(coding_file_types.get_file_types()))
    type_ids = {item["type_id"] for item in registry["data"]["file_types"]}
    assert {"project_readme", "license_doc", "dockerfile", "env_example", "blocked_secret_env"} <= type_ids

    expected = {
        "README.md": "project_readme",
        "LICENSE": "license_doc",
        "CHANGELOG.md": "changelog_doc",
        "Dockerfile": "dockerfile",
        ".gitignore": "gitignore",
        ".env": "blocked_secret_env",
        ".env.example": "env_example",
        "package-lock.json": "package_lock_json",
        "Cargo.lock": "cargo_lock",
        "pyproject.toml": "pyproject_toml",
        "requirements.txt": "requirements_txt",
        "tsconfig.json": "tsconfig_json",
        "vite.config.ts": "vite_config_ts",
        "crlf.txt": "plain_text",
        "NO_EXTENSION": "unknown_text",
        "bidi.txt": "plain_text",
        "small.csv": "csv_data",
        "small.tsv": "tsv_data",
        "malformed.json": "json_data",
        "malformed.yaml": "yaml_data",
        "index.html": "html_markup",
        "binary.bin": "binary",
        "large.txt": "plain_text",
    }
    for filename, type_id in expected.items():
        payload = asyncio.run(
            _await_payload(
                coding_file_types.post_file_inspect_type(
                    coding_file_types.CodingFileTypeInspectRequest(
                        workspace_root=str(tmp_path),
                        file_path=filename,
                    )
                )
            )
        )
        assert payload["data"]["file_type_inspection"]["descriptor"]["type_id"] == type_id
        assert str(tmp_path) not in repr(payload)
        assert "real_secret_value" not in repr(payload)


def test_testclient_read_preview_enforces_metadata_redaction_and_bounds(tmp_path):
    import asyncio

    _write_fixture_matrix(tmp_path)

    env_response = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path=".env",
                    approval_granted=True,
                )
            )
        )
    )
    env_preview = env_response["data"]["file_preview"]
    assert env_preview["status"] == "blocked"
    assert env_preview["source_contents_included"] is False
    assert "real_secret_value" not in repr(env_response)

    example_response = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path=".env.example",
                    approval_granted=True,
                )
            )
        )
    )
    example_preview = example_response["data"]["file_preview"]
    assert example_preview["status"] == "completed"
    assert example_preview["file_type_id"] == "env_example"
    assert example_preview["risk_flags"]["secret_sensitive"] is True
    assert example_preview["secret_scan_findings"]
    assert example_preview["redactions"]
    assert "replace_this_secret" not in repr(example_response)
    assert str(tmp_path) not in repr(example_response)

    large_response = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="large.txt",
                    approval_granted=True,
                    max_lines=5,
                )
            )
        )
    )
    large_preview = large_response["data"]["file_preview"]
    assert large_preview["truncated"] is True
    assert large_preview["lines_returned"] == 5
    assert large_preview["line_count"] > large_preview["lines_returned"]

    html_response = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="index.html",
                    approval_granted=True,
                )
            )
        )
    )
    html_preview = html_response["data"]["file_preview"]
    assert html_preview["parse_summary"]["script_or_style_present"] is True

    bidi_response = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="bidi.txt",
                    approval_granted=True,
                )
            )
        )
    )
    assert "Bidirectional Unicode control markers detected" in " ".join(
        bidi_response["data"]["file_preview"]["redactions"]
    )


def test_malformed_and_binary_preview_truth(tmp_path):
    import asyncio

    _write_fixture_matrix(tmp_path)

    malformed_json = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="malformed.json",
                    approval_granted=True,
                )
            )
        )
    )["data"]["file_preview"]
    assert malformed_json["parse_status"] == "invalid"
    assert "parser_error" in malformed_json["parse_summary"]

    malformed_yaml = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="malformed.yaml",
                    approval_granted=True,
                )
            )
        )
    )["data"]["file_preview"]
    assert malformed_yaml["parse_status"] == "invalid"

    binary = asyncio.run(
        _await_payload(
            coding_files.post_file_read_preview(
                coding_files.CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path="binary.bin",
                    approval_granted=True,
                )
            )
        )
    )["data"]["file_preview"]
    assert binary["status"] == "blocked"
    assert binary["blocked_reason"] == "binary_or_unsupported_file"


def test_file_type_gate_is_shared_by_patch_validation_and_apply(tmp_path):
    _write_fixture_matrix(tmp_path)
    allowed, blocked = validate_patch_targets(str(tmp_path), ["README.md", ".env", "binary.bin"])
    assert "README.md" in allowed
    assert {item["path"]: item["reason"] for item in blocked}[".env"] in {
        "blocked_file_name",
        "file_type_not_patchable",
    }
    assert {item["path"]: item["reason"] for item in blocked}["binary.bin"] == "file_type_not_patchable"

    source = tmp_path / "tsconfig.json"
    old = source.read_text(encoding="utf-8")
    new = '{"compilerOptions": '
    diff = _diff(old, new, "tsconfig.json")
    result = apply_patch_with_approval(
        CodingPatchApplyRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            target_file="tsconfig.json",
            proposed_diff=diff,
            expected_content_hash=sha256(old.encode("utf-8")).hexdigest(),
            patch_hash=patch_hash_for_diff(diff),
            operator_approved=True,
        )
    )

    assert result.status == "blocked"
    assert "JSONDecodeError" in (result.blocked_reason or "")
    assert source.read_text(encoding="utf-8") == old


def test_file_type_gate_is_shared_by_file_operation_planning_and_execution(tmp_path):
    _write_fixture_matrix(tmp_path)

    env_plan = plan_file_operation(
        CodingFileOperationPlanRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="delete",
            target_path=".env",
            summary="delete env",
        )
    )
    assert env_plan.status == "blocked"

    create_env = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path=".env",
            summary="create env",
            new_text="TOKEN=secret\n",
            operator_approved=True,
        )
    )
    assert create_env.status == "blocked"

    create_example_request = CodingFileOperationPlanRequest(
        approval_mode="apply_with_approval",
        workspace_root=str(tmp_path),
        operation_kind="create",
        target_path="new.env.example",
        summary="create env example",
        new_text="TOKEN=replace_me\n",
    )
    create_example_plan = plan_file_operation(create_example_request)
    create_example_approval = approval_fields_for_plan(
        workspace_root=str(tmp_path),
        operation_kind="file_operation:create",
        mutation_class="file_create",
        source_file="new.env.example",
        plan=create_example_plan,
    )
    create_example = execute_file_operation(
        CodingFileOperationExecuteRequest(
            **create_example_request.to_payload(),
            operator_approved=True,
            **create_example_approval,
        )
    )
    assert create_example.status == "applied"
    assert (tmp_path / "new.env.example").exists()

    rename_binary = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="rename",
            target_path="README.md",
            destination_path="binary.bin",
            summary="rename into unsupported binary-looking path",
            operator_approved=True,
        )
    )
    assert rename_binary.status == "blocked"
    assert rename_binary.blocked_reason == "destination_exists"
