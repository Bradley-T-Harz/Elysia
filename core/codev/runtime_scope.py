"""Trusted, in-process context ceiling for Codev's use of Elysia cognition.

HTTP request hints cannot create this context. Both native and browser adapters
enter it only after checking their independently issued workspace grants.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256

from core.codev.contracts import BrowserEditProposal, WorkspaceFile

# Both clients allow 240 seconds for transport. Reserve time for final
# authority checks and delivery; planning and provider preflight share this
# deadline with generation. No HTTP field can extend it.
CHAT_BUDGET_SECONDS = 210.0


@dataclass(frozen=True)
class DevelopmentContext:
    workspace_id: str
    files: tuple[WorkspaceFile, ...] = ()
    handoff: str = ""
    deadline_monotonic: float | None = None
    edit_proposal: bool = False

    def proposal_schema(self):
        if not self.edit_proposal:
            return None
        schema = BrowserEditProposal.model_json_schema()
        schema["properties"]["edits"] = {
            "type": "object", "minProperties": 1, "maxProperties": 20,
            "properties": {item.path: {"type": "string"} for item in self.files if item.text is not None},
            "additionalProperties": False,
        }
        return schema

    def candidates(self, owner_user_id):
        from app.cognition.models import CognitionCandidate, estimate_tokens
        items = [(item.path, f"File: {item.path}\nSHA-256: {item.content_hash}\n{item.text}")
                 for item in self.files if item.text is not None]
        if self.handoff:
            items.append(("conversation-handoff", "Explicitly shared conversation context:\n" + self.handoff[:16000]))
        return [CognitionCandidate(candidate_id="codev_" + sha256((self.workspace_id + name).encode()).hexdigest()[:24],
            source_type="codev_workspace", source_id=self.workspace_id, owner_user_id=owner_user_id,
            space_id=None, privacy="private", form="working", scope="request",
            content_excerpt_or_pointer=content, source_authority="explicit_workspace_grant",
            estimated_tokens=estimate_tokens(content), user_confirmed=True, untrusted=True,
            provenance={"explicitly_shared": True, "instructions_authoritative": False})
            for name, content in items]


_CONTEXT: ContextVar[DevelopmentContext | None] = ContextVar("codev_development_context", default=None)


def current_context() -> DevelopmentContext | None:
    return _CONTEXT.get()


@contextmanager
def development_context(context: DevelopmentContext):
    token = _CONTEXT.set(context)
    try:
        yield
    finally:
        _CONTEXT.reset(token)
