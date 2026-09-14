from hashlib import sha256
import json

from app.cognition import workspace
from core.codev.contracts import WorkspaceFile
from core.codev.runtime_scope import DevelopmentContext, development_context, current_context


def test_typed_edit_proposal_keeps_coding_routing_and_replaces_only_presentation_guidance():
    from core import runtime
    kwargs = {"intent": {"primary": "writing"}, "mode": "coder",
              "selected_skill": {"selected_skill_id": "conversation.conversation_helper"}}
    assert runtime._derive_model_routing_task_type(**kwargs) == "conversation"
    with development_context(DevelopmentContext("proposal-test", edit_proposal=True)):
        assert runtime._derive_model_routing_task_type(**kwargs) == "coding"
        guidance = runtime._build_mode_coder_guidance_block("coder")
        assert "JSON" in guidance and "exact review and approval" in guidance
        assert "Repo Context, Patch Plan" not in guidance
    assert "Repo Context, Patch Plan" in runtime._build_mode_coder_guidance_block("coder")


def test_codev_uses_only_explicit_context_and_never_queries_personal_sources(monkeypatch):
    class ForbiddenSource:
        source_type = "private_canary"
        def __init__(self, **kwargs):
            raise AssertionError("Private source was accessed")
    def forbidden(*args, **kwargs):
        raise AssertionError("Personal memory projection was accessed")
    monkeypatch.setattr(workspace, "DEFAULT_SOURCES", (ForbiddenSource,))
    monkeypatch.setattr(workspace, "FtsMemoryProjection", forbidden)
    text = "answer = 42\n"
    file = WorkspaceFile(path="main.py", text=text, content_hash=sha256(text.encode()).hexdigest(),
                         size_bytes=len(text), availability="text", provenance="local_file")
    with development_context(DevelopmentContext("workspace-a", (file,))):
        result = workspace.build_global_working_workspace(message="Explain answer", owner_user_id="local-a",
            conversation_id=None, project_id=None, request_id="codev_scope_test", mode="coder",
            intent={"primary": "coding"}, model_runtime_tag="local-fixture", model_context_window=32768,
            profile_context={"name": "PRIVATE_PROFILE_CANARY"}, explicit_sealed_memory=True)
    assert text.strip() in result.context_text
    assert "PRIVATE_PROFILE_CANARY" not in result.context_text
    assert {candidate.source_type for candidate in result.admitted_candidates} == {"codev_workspace"}
    assert not result.receipt.excluded
    assert text not in json.dumps(result.receipt.to_payload())
    assert current_context() is None


def test_large_granted_context_still_obeys_existing_model_budget():
    text = "untrusted = 'content'\n" * 5000
    file = WorkspaceFile(path="large.py", text=text, content_hash=sha256(text.encode()).hexdigest(),
                         size_bytes=len(text), availability="text", provenance="local_file")
    with development_context(DevelopmentContext("workspace-a", (file,))):
        result = workspace.build_global_working_workspace(message="Explain this file", owner_user_id="local-a",
            conversation_id=None, project_id=None, request_id="codev_budget_test", mode="coder",
            intent={"primary": "coding"}, model_runtime_tag="small-local", model_context_window=4096)
    assert not result.admitted_candidates
    assert any(item["reason"] == "retrieval_token_budget" for item in result.receipt.excluded)


def test_existing_tool_paths_cannot_expand_a_scoped_codev_request():
    from core import runtime
    policy = {"allowed": True, "boundary_flags": ["bounded_local_math_execution", "bounded_local_data_execution", "repo_context", "code_patch_plan", "aider_worker"]}
    plan = {"bounded_math_execution_candidate": True, "bounded_data_execution_candidate": True,
            "repo_context_candidate": True, "code_patch_plan_candidate": True, "aider_worker_candidate": True}
    with development_context(DevelopmentContext("workspace-a")):
        for predicate in (runtime._should_run_bounded_math_execution, runtime._should_run_bounded_data_execution,
                          runtime._should_run_repo_context, runtime._should_run_code_patch_plan):
            assert not predicate(plan=plan, policy_review=policy)
        assert not runtime._should_run_aider_worker_validation(plan=plan, code_patch_plan={"used": True, "status": "completed"})


def test_codev_model_transport_refuses_proxy_redirect_and_remote_provider(monkeypatch):
    from core import model_invoker
    from core.codev.grants import GrantDenied
    import pytest
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return "literal-local-response"
    def opener(*handlers):
        assert handlers[0].proxies == {}
        with pytest.raises(GrantDenied, match="redirect"):
            handlers[1].redirect_request(None, None, None, None, None, "https://attacker.invalid")
        return Opener()
    monkeypatch.setattr(model_invoker.urllib_request, "build_opener", opener)
    monkeypatch.setattr(model_invoker.urllib_request, "urlopen", lambda *a, **k: pytest.fail("Inherited provider/proxy transport accessed"))
    with development_context(DevelopmentContext("workspace-a")):
        for url in ["https://provider.invalid/api/chat", "http://localhost:11434/api/chat", "http://127.0.0.1:11434/api/chat?destination=remote", "http://127.0.0.1:11434/api/pull"]:
            with pytest.raises(GrantDenied): model_invoker._provider_open(url, timeout=1)
        assert model_invoker._provider_open("http://127.0.0.1:11434/api/chat", timeout=1) == "literal-local-response"
    assert len(calls) == 1
