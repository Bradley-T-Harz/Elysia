"""Bounded deterministic chat for approved Codev context.

This is deliberately not presented as a general coding-reasoning model. The
only source-to-patch transform here is the retained Fibonacci fixture used by
the bridge contract tests; all other files receive honest bounded-context
truth and must use a separately reviewed diff or a future governed reasoner.
"""

from __future__ import annotations

import difflib
from hashlib import sha256

from app.api.coding_approval_modes import approval_mode_policy, mode_required_message
from app.api.coding_policy_service import coding_boundary_flags_for_mode
from app.api.coding_patch_service import patch_hash_for_diff, propose_patch
from app.api.schemas.coding import CodingChatRequest, CodingChatResult
from app.api.schemas.coding_patch import CodingPatchProposeRequest


REFUSED_CAPABILITIES = [
    "patch_apply",
    "command_execution",
    "test_execution",
    "git_mutation",
    "package_manager",
    "autonomous_loop",
]


def _context_receipt(payload: CodingChatRequest) -> dict[str, object]:
    safe_items = []
    blocked = 0
    for item in payload.selected_context:
        relative = item.relative_path.replace("\\", "/").strip()
        lowered = relative.casefold()
        if (
            not relative
            or relative.startswith("/")
            or ".." in relative.split("/")
            or any(part in lowered.split("/") for part in {".env", ".git", "secrets", "credentials", "vault", "memory", "journals", "logs"})
        ):
            blocked += 1
            continue
        safe_items.append(
            {
                "relative_path": relative,
                "context_kind": item.context_kind,
                "scm_status": item.scm_status,
                "staged": item.staged,
                "source_contents_included": False,
            }
        )
    approved_preview = payload.approved_file_context
    return {
        "selected_metadata": safe_items,
        "selected_metadata_count": len(safe_items),
        "blocked_metadata_count": blocked,
        "approved_source_preview_included": bool(
            approved_preview
            and approved_preview.approval_granted
            and approved_preview.source_contents_included
        ),
        "broad_repo_snapshot_included": False,
        "raw_absolute_paths_included": False,
    }


def _looks_like_patch_request(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in ("patch", "diff", "fix", "edit", "change", "modify", "rewrite", "replace"))


def _looks_like_debug_question(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in ("wrong", "bug", "why", "explain", "debug", "issue", "problem", "fix"))


def _detect_fibonacci_overwrite_bug(source: str) -> bool:
    normalized = "\n".join(line.rstrip() for line in source.splitlines())
    return "def fibonacci" in normalized and "a = b" in normalized and "b = a + b" in normalized


def _fibonacci_explanation(file_label: str) -> str:
    return (
        f"In `{file_label}`, the Fibonacci update is using overwritten state. Inside the loop, "
        "`a = b` runs first, so when `b = a + b` executes, `a` is no longer the old previous value; "
        "it is already the old `b`. That makes the sequence advance incorrectly. The usual safe update "
        "keeps both old values for the same step, for example `a, b = b, a + b`. Depending on whether "
        "`fibonacci(1)` should be 1 and `fibonacci(2)` should be 1, the loop count may also need to be "
        "checked, but the main bug is the sequential overwrite."
    )


def _fixed_fibonacci_source(source: str) -> str:
    return source.replace(
        "    for _ in range(n):\n        a = b\n        b = a + b\n",
        "    for _ in range(1, n):\n        a, b = b, a + b\n",
    )


def _fibonacci_patch_diff(relative_path: str, source: str) -> str:
    return "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            _fixed_fibonacci_source(source).splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )


def handle_coding_chat(payload: CodingChatRequest) -> CodingChatResult:
    workspace_label = payload.workspace_label or "this workspace"
    mode_policy = approval_mode_policy(payload.approval_mode)
    context = payload.approved_file_context
    flags = coding_boundary_flags_for_mode(mode_policy.mode)
    context_receipt = _context_receipt(payload)
    if context and context.approval_granted and context.source_contents_included:
        source = context.content_preview
        relative_path = context.relative_path
        file_label = context.file_label
        plan = [
            f"Use the approved bounded preview for {relative_path}.",
            "Explain or propose changes without applying patches.",
            "Keep patch application, commands, tests, git mutation, and package managers disabled.",
        ]
        patch_payload = None
        if _detect_fibonacci_overwrite_bug(source):
            assistant_text = _fibonacci_explanation(file_label)
            if _looks_like_patch_request(payload.message) and mode_policy.can_propose_patch:
                diff_text = _fibonacci_patch_diff(relative_path, source)
                patch = propose_patch(
                    CodingPatchProposeRequest(
                        session_id=payload.session_id,
                        approval_mode=mode_policy.mode,
                        workspace_root=".",
                        target_files=[relative_path],
                        change_summary=(
                            "Preview-only fix for Fibonacci state overwrite: update a and b together "
                            "and adjust the loop to preserve the expected indexing."
                        ),
                        proposed_diff=diff_text,
                    )
                )
                patch_payload = patch.to_payload()
                patch_payload["expected_content_hash"] = sha256(source.encode("utf-8")).hexdigest()
                patch_payload["patch_hash"] = patch_hash_for_diff(diff_text)
                assistant_text = (
                    f"{assistant_text}\n\nI prepared a preview-only patch proposal. No files were changed."
                )
            elif _looks_like_patch_request(payload.message):
                assistant_text = (
                    f"{assistant_text}\n\nI did not prepare an apply-ready patch because the current approval mode is "
                    f"`{mode_policy.mode}`. {mode_required_message('apply_with_approval')}"
                )
        else:
            assistant_text = (
                f"I received the approved bounded preview for `{relative_path}` ({len(source.splitlines())} visible lines). "
                "This `/coding/chat` implementation is currently a deterministic safety bridge, not a general "
                "coding-reasoning model. Its only automatic source transform is the explicitly contained "
                "Fibonacci contract fixture, which does not match this preview. I will not invent a diagnosis "
                "or patch. You can still submit a reviewed unified diff to the governed patch proposal surface; "
                "apply, checks, and file operations remain separate exact-approval workflows."
            )
            if _looks_like_debug_question(payload.message):
                assistant_text += " General local coding reasoning remains a visible capability gap."
        return CodingChatResult(
            session_id=payload.session_id,
            assistant_text=assistant_text,
            approval_mode=mode_policy.mode,
            plan=plan,
            refused_capabilities=REFUSED_CAPABILITIES,
            boundaries=flags,
            used_approved_file_context=True,
            patch_proposal=patch_payload,
            context_receipt=context_receipt,
        )

    if _looks_like_patch_request(payload.message) or _looks_like_debug_question(payload.message):
        assistant_text = (
            "Approve a file preview first. Codev has not sent source contents for this session yet, "
            "so I will not pretend I have read the active file. Once a bounded preview is approved, "
            "I can explain the code or prepare a preview-only patch proposal without applying it."
        )
        plan = [
            "Open the target file in VS Code.",
            "Use Read approved preview in Codev.",
            "Ask the question again after the approved context is visible.",
        ]
        return CodingChatResult(
            session_id=payload.session_id,
            assistant_text=assistant_text,
            approval_mode=mode_policy.mode,
            plan=plan,
            refused_capabilities=REFUSED_CAPABILITIES,
            boundaries=flags,
            used_approved_file_context=False,
            context_receipt=context_receipt,
        )

    assistant_text = (
        "This chat endpoint can explain its governed boundaries and accept an approved bounded file preview, "
        "but it does not yet have a general coding-reasoning model. Separate Codev controls can propose a "
        "reviewed diff, consume exact one-time approval for mutation, and run exact allowlisted checks. "
        "Chat itself will not mutate files, execute commands, mutate git, install packages, upload code, "
        "or start an autonomous loop."
    )
    plan = [
        f"Clarify the requested change for {workspace_label}.",
        "Use repo inspection preview metadata only unless a future explicit file-read contract is approved.",
        "Use the governed patch/file/check panels for exact approved operations; do not treat chat as a general code agent.",
    ]
    return CodingChatResult(
        session_id=payload.session_id,
        assistant_text=assistant_text,
        approval_mode=mode_policy.mode,
        plan=plan,
        refused_capabilities=REFUSED_CAPABILITIES,
        boundaries=flags,
        context_receipt=context_receipt,
    )


__all__ = ("REFUSED_CAPABILITIES", "handle_coding_chat")
