"""Language-aware metadata for supported Codev code files."""

from __future__ import annotations

from app.api.coding_file_type_registry import CodingFileTypeDescriptor


LANGUAGE_HINTS: dict[str, dict[str, object]] = {
    "python": {
        "comment_syntax": "#",
        "dependency_markers": ("import ", "from "),
        "test_file_patterns": ("test_*.py", "*_test.py"),
        "safe_checks": ("python -m py_compile", "pytest allowlist only"),
    },
    "typescript": {"comment_syntax": "//", "dependency_markers": ("import ", "from "), "safe_checks": ("npm run typecheck allowlist only",)},
    "typescriptreact": {"comment_syntax": "//", "dependency_markers": ("import ", "from "), "safe_checks": ("npm run typecheck allowlist only",)},
    "javascript": {"comment_syntax": "//", "dependency_markers": ("import ", "require("), "safe_checks": ("npm script allowlist only",)},
    "javascriptreact": {"comment_syntax": "//", "dependency_markers": ("import ", "require("), "safe_checks": ("npm script allowlist only",)},
    "css": {"comment_syntax": "/* */", "dependency_markers": ("@import",), "safe_checks": ()},
    "sql": {"comment_syntax": "--", "dependency_markers": (), "safe_checks": (), "risk_notes": ("SQL execution is not enabled.",)},
    "shellscript": {"comment_syntax": "#", "dependency_markers": (), "safe_checks": (), "risk_notes": ("Shell execution is not implied and remains governed separately.",)},
    "dockerfile": {"comment_syntax": "#", "dependency_markers": ("FROM ", "RUN "), "safe_checks": (), "risk_notes": ("Docker build/run is not enabled.",)},
    "pip-requirements": {"comment_syntax": "#", "dependency_markers": (), "safe_checks": (), "risk_notes": ("Package installation is not enabled.",)},
}


def summarize_code_file(descriptor: CodingFileTypeDescriptor, text: str) -> dict[str, object]:
    hints = dict(LANGUAGE_HINTS.get(descriptor.language_id or "", {}))
    import_like_lines: list[str] = []
    markers = tuple(str(item) for item in hints.get("dependency_markers", ()))
    for line in text.splitlines()[:240]:
        stripped = line.strip()
        if markers and stripped.startswith(markers):
            import_like_lines.append(stripped[:180])
        if len(import_like_lines) >= 20:
            break
    hints["import_or_dependency_markers_seen"] = import_like_lines
    hints["safe_patch_style"] = "unified_diff_text_patch"
    return hints


__all__ = ("LANGUAGE_HINTS", "summarize_code_file")
