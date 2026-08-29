from __future__ import annotations

from app.api.coding_chat_service import handle_coding_chat
from app.api.schemas.coding import ApprovedFileContext, CodingChatRequest


FIBONACCI_BUG = """def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1

    a = 0
    b = 1

    for _ in range(n):
        a = b
        b = a + b

    return b
"""


def test_coding_chat_refuses_file_specific_question_without_approved_context():
    result = handle_coding_chat(
        CodingChatRequest(message="What is wrong with fibonacci_bug.py?")
    )

    assert result.used_approved_file_context is False
    assert "Approve a file preview first" in result.assistant_text
    assert result.patch_proposal is None


def test_coding_chat_uses_approved_file_context_for_fibonacci_debugging():
    result = handle_coding_chat(
        CodingChatRequest(
            message="What is wrong with fibonacci_bug.py?",
            approved_file_context=ApprovedFileContext(
                file_label="fibonacci_bug.py",
                relative_path="fibonacci_bug.py",
                language_hint="python",
                path_hash="abc123",
                content_preview=FIBONACCI_BUG,
            ),
        )
    )

    assert result.used_approved_file_context is True
    assert "a = b" in result.assistant_text
    assert "b = a + b" in result.assistant_text
    assert "overwritten" in result.assistant_text


def test_coding_chat_returns_preview_only_patch_proposal_for_fix_request():
    result = handle_coding_chat(
        CodingChatRequest(
            approval_mode="apply_with_approval",
            message="Please fix fibonacci_bug.py with a patch.",
            approved_file_context=ApprovedFileContext(
                file_label="fibonacci_bug.py",
                relative_path="fibonacci_bug.py",
                language_hint="python",
                path_hash="abc123",
                content_preview=FIBONACCI_BUG,
            ),
        )
    )

    assert result.patch_proposal is not None
    assert result.patch_proposal["status"] == "preview_only"
    assert result.patch_proposal["apply_allowed"] is True
    assert "a, b = b, a + b" in (result.patch_proposal["diff_preview"] or "")
    assert result.patch_proposal["diff_preview"].endswith("\n")


def test_coding_chat_does_not_prepare_patch_in_plan_only():
    result = handle_coding_chat(
        CodingChatRequest(
            approval_mode="plan_only",
            message="Please fix fibonacci_bug.py with a patch.",
            approved_file_context=ApprovedFileContext(
                file_label="fibonacci_bug.py",
                relative_path="fibonacci_bug.py",
                language_hint="python",
                path_hash="abc123",
                content_preview=FIBONACCI_BUG,
            ),
        )
    )

    assert result.patch_proposal is None
    assert "current approval mode is `plan_only`" in result.assistant_text
    assert "apply_with_approval" in result.assistant_text


def test_coding_chat_honestly_contains_non_fixture_reasoning_gap():
    result = handle_coding_chat(
        CodingChatRequest(
            approval_mode="apply_with_approval",
            message="Please diagnose and patch this function.",
            approved_file_context=ApprovedFileContext(
                file_label="worker.py",
                relative_path="src/worker.py",
                language_hint="python",
                path_hash="abc123",
                content_preview="def work(value):\n    return value\n",
            ),
        )
    )

    assert result.patch_proposal is None
    assert "not a general coding-reasoning model" in result.assistant_text
    assert "will not invent" in result.assistant_text
