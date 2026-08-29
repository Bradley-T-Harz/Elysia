"""Production normal-memory semantic projection over local Ollama + Qdrant.

Canonical SQLite Memory remains the sole writer and authority. This module
only maintains a disposable derived projection. It accepts authenticated
loopback services, persists vectors for normal Memory only, and re-authorizes
every returned identifier against canonical Memory before workspace use.
Private Memory keeps its authenticated process-local retrieval path. Sealed
Memory is never embedded or persisted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import stat
from time import perf_counter
from typing import Any, Iterable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from app.install.paths import ElysiaPaths, ensure_memory_directories, resolve_elysia_paths
from app.memory.canonical_models import MemoryPrivacy, MemoryQuery
from app.memory.canonical_repository import MemoryRepository, utc_now
from app.memory.fabric_service import MemoryFabricService
from app.cognition.compute_governor import (
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
)
from app.cognition.emergency_control import emergency_active
from app.cognition.model_registry import ModelRegistry, model_resource_estimate
from app.ids import new_id


SEMANTIC_ABSTRACTION_VERSION = "normal-memory-hybrid-semantic-v2"
SEMANTIC_BENCHMARK_VERSION = "part2c-loopback-qdrant-server-reconsideration-v1"
SEMANTIC_PROMOTION_DECISION = "promoted_optional_local_profile"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EMBEDDING_DIMENSION = 1024
PREPROCESSING_VERSION = "unicode-nfkc-whitespace-collapse-v1"
COLLECTION = "elysia_memory_semantic_v1"
POINT_NAMESPACE = f"urn:elysia:{COLLECTION}:"
MAX_HTTP_BYTES = 32 * 1024 * 1024


class SemanticProjectionError(RuntimeError):
    """A local semantic dependency failed without exposing secrets/content."""


class SemanticProjectionUnavailable(SemanticProjectionError):
    """The explicitly selected optional semantic profile is unavailable."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _loopback_url(value: str, *, label: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SemanticProjectionError(f"{label} must be a plain loopback HTTP origin.")
    try:
        address = ipaddress.ip_address(str(parsed.hostname or ""))
    except ValueError as exc:
        raise SemanticProjectionError(f"{label} must use the explicit 127.0.0.1 address.") from exc
    if address != ipaddress.ip_address("127.0.0.1"):
        raise SemanticProjectionError(f"{label} must use the explicit 127.0.0.1 address.")
    if not parsed.port:
        raise SemanticProjectionError(f"{label} must declare its loopback port.")
    return f"http://127.0.0.1:{parsed.port}"


def _private_regular_file(path: Path, *, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise SemanticProjectionError(f"{label} is not a safe regular file.")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SemanticProjectionError(f"{label} permissions are too broad.")
    return path


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split())[:24_000]


def _point_id(memory_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, POINT_NAMESPACE + str(memory_id)))


def _record_text(record: Any) -> str:
    return _normalize("\n".join(value for value in (
        str(record.title or ""), str(record.body or ""), str(record.why_stored or "")
    ) if value))


def _linked_id(record: Any, target_type: str) -> str | None:
    for relation in list(getattr(record, "relations", []) or []):
        if str(relation.get("target_type")) == target_type:
            return str(relation.get("target_id") or "") or None
    return None


@dataclass(frozen=True)
class SemanticProjectionConfig:
    enabled: bool
    qdrant_url: str
    api_key_path: Path
    ollama_url: str
    collection: str = COLLECTION
    model: str = EMBEDDING_MODEL
    embedding_num_gpu: int = 0

    @classmethod
    def load(cls, paths: ElysiaPaths) -> "SemanticProjectionConfig | None":
        config_path = paths.memory_semantic_client_config_path
        if not config_path.exists():
            return None
        _private_regular_file(config_path, label="Semantic client configuration")
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SemanticProjectionError("Semantic client configuration is invalid.") from exc
        if not isinstance(payload, dict) or int(payload.get("version") or 0) != 1:
            raise SemanticProjectionError("Semantic client configuration version is unsupported.")
        key_name = str(payload.get("api_key_file") or "api-key")
        if Path(key_name).is_absolute() or Path(key_name).name != key_name:
            raise SemanticProjectionError("Semantic API-key reference must remain inside its XDG config directory.")
        collection = str(payload.get("collection") or COLLECTION)
        model = str(payload.get("embedding_model") or EMBEDDING_MODEL)
        if collection != COLLECTION or model != EMBEDDING_MODEL:
            raise SemanticProjectionError("Semantic collection/model contract does not match this Elysia release.")
        try:
            embedding_num_gpu = int(payload.get("embedding_num_gpu", 0))
        except (TypeError, ValueError) as exc:
            raise SemanticProjectionError("Semantic embedding device policy is invalid.") from exc
        if embedding_num_gpu not in {-1, 0}:
            raise SemanticProjectionError(
                "Semantic embedding policy must be governed automatic (-1) or deterministic CPU fallback (0)."
            )
        return cls(
            enabled=payload.get("enabled") is True,
            qdrant_url=_loopback_url(str(payload.get("qdrant_url") or ""), label="Qdrant URL"),
            api_key_path=paths.memory_semantic_config_dir / key_name,
            ollama_url=_loopback_url(str(payload.get("ollama_url") or ""), label="Ollama URL"),
            collection=collection,
            model=model,
            embedding_num_gpu=embedding_num_gpu,
        )


class SemanticMemoryProjection:
    """Authenticated REST client and canonical projection coordinator.

    Packaged Core deliberately uses only the standard library. qdrant-client
    remains a benchmark/developer dependency rather than a Core dependency.
    """

    def __init__(
        self,
        *,
        paths: ElysiaPaths | None = None,
        repository: MemoryRepository | None = None,
        fabric: MemoryFabricService | None = None,
        config: SemanticProjectionConfig | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.repository = repository or MemoryRepository(paths=self.paths)
        self.fabric = fabric or MemoryFabricService(repository=self.repository)
        self.config = config if config is not None else SemanticProjectionConfig.load(self.paths)

    def _current_space_ids(
        self, principal: Any, requested: Iterable[str] | None = None
    ) -> list[str]:
        requested_set = (
            {str(value) for value in requested if str(value)}
            if requested is not None
            else None
        )
        with self.repository.connect() as canonical:
            rows = canonical.execute(
                "SELECT space_id FROM shared_space_members WHERE user_id=? ORDER BY space_id",
                (principal.user_id,),
            ).fetchall()
        current = [str(row["space_id"]) for row in rows]
        if requested_set is None:
            return current
        return [space_id for space_id in current if space_id in requested_set]

    def _authorization_signature(self, principal: Any) -> str:
        spaces = self._current_space_ids(principal)
        payload = "\0".join([str(principal.user_id), *spaces]).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def configured(self) -> bool:
        return self.config is not None and self.config.enabled

    def _api_key(self) -> str:
        if self.config is None or not self.config.enabled:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not enabled.")
        key = _private_regular_file(self.config.api_key_path, label="Qdrant API key").read_text(
            encoding="utf-8"
        ).strip()
        if len(key) < 32:
            raise SemanticProjectionError("The local Qdrant API key is invalid.")
        return key

    @staticmethod
    def _decode(response: Any) -> dict[str, Any]:
        raw = response.read(MAX_HTTP_BYTES + 1)
        if len(raw) > MAX_HTTP_BYTES:
            raise SemanticProjectionError("A local semantic dependency exceeded its response limit.")
        if not raw:
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise SemanticProjectionError("A local semantic dependency returned an invalid contract.")
        return payload

    def _qdrant(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_missing: bool = False,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        if self.config is None:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not configured.")
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.config.qdrant_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "api-key": self._api_key()},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return self._decode(response)
        except HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None
            raise SemanticProjectionError(f"Local Qdrant rejected the governed request (HTTP {exc.code}).") from exc
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise SemanticProjectionUnavailable("The authenticated loopback Qdrant service is unavailable.") from exc

    def _ollama(
        self,
        texts: list[str],
        *,
        principal: Any,
        background: bool = False,
        timeout: float = 120.0,
    ) -> list[list[float]]:
        if self.config is None:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not configured.")
        bounded = [_normalize(value) for value in texts]
        if not bounded or any(not value for value in bounded):
            raise SemanticProjectionError("Embedding input must contain bounded nonempty text.")
        # Resource and device choices must consume the same effective account
        # controls as the live runtime. That merge includes managed-profile
        # ceilings; reading raw Memory settings here would let a derived
        # projection escape installation governance.
        from app.api.user_control_service import current_user_controls

        controls = current_user_controls()
        model_resources = model_resource_estimate(
            ModelRegistry(self.paths).snapshot(), self.config.model
        )
        compute = decide_compute(
            WorkloadDescriptor(
                workload_id=new_id("embedding"),
                owner_user_id=str(principal.user_id),
                task_kind="semantic_embedding_batch" if len(bounded) > 1 else "semantic_query_embedding",
                priority="background" if background else "interactive",
                interactive=not background,
                privacy="normal",
                estimated_cpu_percent=35,
                estimated_ram_mb=int(model_resources["estimated_ram_mb"]),
                estimated_vram_mb=int(model_resources["estimated_vram_mb"]),
                incremental_vram_mb=int(model_resources["incremental_vram_mb"]),
                estimated_duration_ms=max(500, len(bounded) * 250),
                batchable=True,
                cancellable=True,
                preemptible=background,
                cpu_fallback_allowed=True,
                required_model=self.config.model,
                required_resources=("local_ollama_embedding",),
                hard_vram_limit_mb=controls.vram_mb_ceiling,
                estimate_source=str(model_resources["measurement_source"]),
            ),
            preference=(
                "cpu" if self.config.embedding_num_gpu == 0
                else controls.compute_preference
            ),
            cpu_percent_ceiling=controls.cpu_percent_ceiling,
            ram_mb_ceiling=controls.ram_mb_ceiling,
            vram_mb_ceiling=controls.vram_mb_ceiling,
            max_background_jobs=controls.max_background_jobs,
            stop_active=emergency_active(self.paths),
            paths=self.paths,
        )
        if compute.decision in {"rejected", "deferred"}:
            raise SemanticProjectionUnavailable("The Compute Governor found no safe embedding path.")
        # Ollama uses -1 for its full automatic GPU offload. Passing 1 means a
        # single layer, which is not truthful CUDA placement for this model.
        num_gpu = -1 if compute.selected_device == "cuda:0" else 0
        request = Request(
            self.config.ollama_url + "/api/embed",
            data=json.dumps(
                {
                    "model": self.config.model,
                    "input": bounded,
                    "truncate": True,
                    "keep_alive": "10m",
                    "options": {"num_gpu": num_gpu},
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = self._decode(response)
        except HTTPError as exc:
            raise SemanticProjectionError(f"Local Ollama rejected embedding (HTTP {exc.code}).") from exc
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise SemanticProjectionUnavailable("The loopback Ollama embedding model is unavailable.") from exc
        finally:
            ledger = ComputeLedger(self.paths)
            observed_resources = model_resource_estimate(
                ModelRegistry(self.paths).snapshot(), self.config.model
            )
            observed_vram_mb = (
                int(observed_resources.get("estimated_vram_mb") or 0)
                if observed_resources.get("measurement_source")
                == "ollama_live_residency_size_vram"
                else None
            )
            if compute.lease_id:
                ledger.release(
                    compute.lease_id,
                    reason="embedding_request_finished",
                    actual_vram_mb=observed_vram_mb,
                )
            if compute.reservation_id:
                ledger.release_job(
                    compute.reservation_id, reason="embedding_request_finished"
                )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(bounded):
            raise SemanticProjectionError("Ollama returned the wrong embedding batch shape.")
        vectors: list[list[float]] = []
        for vector in embeddings:
            if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSION:
                raise SemanticProjectionError("Ollama returned the wrong embedding dimension.")
            values = [float(item) for item in vector]
            if not all(math.isfinite(item) for item in values):
                raise SemanticProjectionError("Ollama returned a nonfinite embedding.")
            vectors.append(values)
        return vectors

    def ensure_collection(self) -> bool:
        """Create the derived normal-only collection and payload indexes."""
        if not self.configured:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not enabled.")
        assert self.config is not None
        path = f"/collections/{self.config.collection}"
        if self._qdrant("GET", path, allow_missing=True, timeout=3.0) is not None:
            return False
        self._qdrant(
            "PUT",
            path,
            {
                "vectors": {"size": EMBEDDING_DIMENSION, "distance": "Cosine", "on_disk": False},
                "hnsw_config": {"m": 16, "ef_construct": 100, "on_disk": False},
                "optimizers_config": {"indexing_threshold": 10_000},
            },
            timeout=30.0,
        )
        for field in (
            "memory_id", "owner_user_id", "space_id", "privacy", "status",
            "scope", "form", "project_id", "conversation_id",
        ):
            self._qdrant(
                "PUT", f"{path}/index?wait=true",
                {"field_name": field, "field_schema": "keyword"}, timeout=30.0,
            )
        self._write_state({"version": SEMANTIC_ABSTRACTION_VERSION, "owners": {}})
        return True

    def _payload(self, record: Any, text: str) -> dict[str, Any]:
        return {
            "memory_id": str(record.memory_id),
            "owner_user_id": str(record.owner_user_id),
            "space_id": str(record.space_id) if record.space_id else None,
            "privacy": "normal",
            "status": str(getattr(record.status, "value", record.status)),
            "scope": str(getattr(record.scope, "value", record.scope)),
            "form": str(getattr(record.form, "value", record.form)),
            "project_id": _linked_id(record, "project"),
            "conversation_id": _linked_id(record, "conversation"),
            "updated_at": str(record.updated_at),
            "content_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_authority": "canonical_memory_fabric",
        }

    def _delete(self, memory_id: str) -> None:
        if self.config is None:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not configured.")
        if self._qdrant(
            "GET", f"/collections/{self.config.collection}", allow_missing=True, timeout=3.0
        ) is None:
            return
        self._qdrant(
            "POST", f"/collections/{self.config.collection}/points/delete?wait=true",
            {"points": [_point_id(memory_id)]}, timeout=30.0,
        )

    def purge_record(self, memory_id: str) -> dict[str, Any]:
        """Eagerly remove a derived vector before privacy/hard-delete commit."""
        if not self.configured:
            return {
                "state": "not_configured", "memory_id": memory_id,
                "canonical_memory_mutated": False,
                "persistent_private_vectors": 0, "persistent_sealed_vectors": 0,
            }
        self._delete(memory_id)
        return {
            "state": "purged", "memory_id": memory_id,
            "canonical_memory_mutated": False,
            "persistent_private_vectors": 0, "persistent_sealed_vectors": 0,
        }

    def verify_record_absent(self, memory_id: str) -> dict[str, Any]:
        if not self.configured:
            return {"absent": True, "state": "not_configured"}
        if self.config is None:
            raise SemanticProjectionUnavailable("The semantic projection configuration is unavailable.")
        collection = self._qdrant(
            "GET", f"/collections/{self.config.collection}",
            allow_missing=True, timeout=3.0,
        )
        if collection is None:
            return {"absent": True, "state": "collection_absent"}
        point = self._qdrant(
            "GET",
            f"/collections/{self.config.collection}/points/{_point_id(memory_id)}",
            allow_missing=True,
            timeout=3.0,
        )
        return {"absent": point is None, "state": "verified"}

    def _upsert_batch(self, records: list[Any], principal: Any) -> int:
        normal = []
        for record in records:
            privacy = str(getattr(record.privacy, "value", record.privacy))
            status = str(getattr(record.status, "value", record.status))
            tier = str(getattr(record.activation_tier, "value", record.activation_tier))
            form = str(getattr(record.form, "value", record.form))
            form_data = getattr(record, "form_data", {}) or {}
            if (
                privacy != "normal"
                or status not in {"active", "working"}
                or tier in {"cold", "archived"}
                or form == "audit"
                or (form == "prospective" and str(form_data.get("state") or "pending") != "pending")
                or bool(getattr(record, "automatic_recall_suppressed", False))
                or (record.valid_until is not None and str(record.valid_until) <= utc_now())
            ):
                self._delete(str(record.memory_id))
                continue
            text = _record_text(record)
            if text:
                normal.append((record, text))
        if not normal:
            return 0
        vectors = self._ollama(
            [text for _record, text in normal], principal=principal, background=True
        )
        points = [
            {"id": _point_id(str(record.memory_id)), "vector": vector,
             "payload": self._payload(record, text)}
            for (record, text), vector in zip(normal, vectors, strict=True)
        ]
        assert self.config is not None
        self._qdrant(
            "PUT", f"/collections/{self.config.collection}/points?wait=true",
            {"points": points}, timeout=120.0,
        )
        return len(points)

    def upsert_record(self, record: Any, principal: Any) -> str:
        self.ensure_collection()
        return "indexed" if self._upsert_batch([record], principal) else "excluded_non_normal_or_inactive"

    def process_pending(self, principal: Any, *, limit: int = 200) -> dict[str, Any]:
        if not self.configured:
            return {"state": "not_configured", "processed": 0, "failed": 0}
        if emergency_active(self.paths):
            return {
                "state": "paused_by_emergency_stop",
                "processed": 0,
                "failed": 0,
            }
        self.ensure_collection()
        self.repository.initialize()
        with self.repository.connect() as canonical:
            jobs = canonical.execute(
                """
                SELECT job_id, job_kind FROM memory_jobs
                WHERE state IN ('pending','failed')
                  AND (job_kind LIKE 'semantic_upsert:%' OR job_kind LIKE 'semantic_delete:%')
                  AND (
                    job_kind LIKE 'semantic_delete:%'
                    OR EXISTS (
                        SELECT 1 FROM memory_records r
                        WHERE r.memory_id = substr(memory_jobs.job_kind, 17)
                          AND (
                            (r.space_id IS NULL AND r.owner_user_id = ?)
                            OR EXISTS (
                                SELECT 1 FROM shared_space_members sm
                                WHERE sm.space_id = r.space_id AND sm.user_id = ?
                            )
                          )
                    )
                  )
                ORDER BY created_at, job_id LIMIT ?
                """,
                (principal.user_id, principal.user_id, max(1, min(limit, 1000))),
            ).fetchall()
        processed = failed = 0
        for job in jobs:
            if emergency_active(self.paths):
                return {
                    "state": "paused_by_emergency_stop",
                    "processed": processed,
                    "failed": failed,
                }
            job_id = str(job["job_id"])
            kind, memory_id = str(job["job_kind"]).split(":", 1)
            result_code = "deleted"
            try:
                if kind == "semantic_delete":
                    self._delete(memory_id)
                else:
                    try:
                        record = self.fabric.get(principal, memory_id)
                    except Exception:
                        self._delete(memory_id)
                        result_code = "missing_or_inaccessible"
                    else:
                        result_code = self.upsert_record(record, principal)
                with self.repository.transaction() as canonical:
                    canonical.execute(
                        "UPDATE memory_jobs SET state='completed', progress_current=1, updated_at=?, result_code=? WHERE job_id=?",
                        (utc_now(), result_code, job_id),
                    )
                processed += 1
            except Exception:
                with self.repository.transaction() as canonical:
                    canonical.execute(
                        "UPDATE memory_jobs SET state='failed', updated_at=?, result_code='semantic_projection_apply_failed' WHERE job_id=?",
                        (utc_now(), job_id),
                    )
                failed += 1
                break
        return {"state": "ready" if failed == 0 else "degraded", "processed": processed, "failed": failed}

    def _read_state(self) -> dict[str, Any]:
        path = self.paths.memory_semantic_state_path
        if not path.exists():
            return {"version": SEMANTIC_ABSTRACTION_VERSION, "owners": {}}
        try:
            payload = json.loads(_private_regular_file(
                path, label="Semantic projection state"
            ).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, SemanticProjectionError):
            return {"version": SEMANTIC_ABSTRACTION_VERSION, "owners": {}}
        return payload if isinstance(payload, dict) else {"version": SEMANTIC_ABSTRACTION_VERSION, "owners": {}}

    def _write_state(self, payload: dict[str, Any]) -> None:
        ensure_memory_directories(self.paths)
        path = self.paths.memory_semantic_state_path
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    def rebuild(self, principal: Any) -> dict[str, Any]:
        if not self.configured:
            raise SemanticProjectionUnavailable("The optional local semantic profile is not enabled.")
        started = perf_counter()
        self.ensure_collection()
        assert self.config is not None
        current_spaces = self._current_space_ids(principal)
        replace_authorization: list[dict[str, Any]] = [
            {
                "must": [
                    {"key": "owner_user_id", "match": {"value": principal.user_id}},
                    {"is_empty": {"key": "space_id"}},
                ]
            }
        ]
        if current_spaces:
            replace_authorization.append(
                {"key": "space_id", "match": {"any": current_spaces}}
            )
        self._qdrant(
            "POST", f"/collections/{self.config.collection}/points/delete?wait=true",
            {"filter": {"should": replace_authorization}},
            timeout=120.0,
        )
        records: list[Any] = []
        offset = 0
        while True:
            page, total = self.fabric.list(
                principal,
                MemoryQuery(privacy=MemoryPrivacy.NORMAL, include_archived=True, limit=200, offset=offset),
            )
            records.extend(page)
            offset += len(page)
            if not page or offset >= total:
                break
        indexed = 0
        for start in range(0, len(records), 32):
            indexed += self._upsert_batch(records[start : start + 32], principal)
        state = self._read_state()
        owners = dict(state.get("owners") or {})
        owners[str(principal.user_id)] = self._authorization_signature(principal)
        self._write_state({"version": SEMANTIC_ABSTRACTION_VERSION, "owners": owners})
        return {
            "state": "ready", "indexed": indexed,
            "excluded_non_normal_or_inactive": max(0, len(records) - indexed),
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "projection_version": SEMANTIC_ABSTRACTION_VERSION,
            "canonical_memory_mutated": False,
        }

    def ensure_ready(self, principal: Any) -> dict[str, Any]:
        created = self.ensure_collection()
        owners = dict(self._read_state().get("owners") or {})
        result = self.rebuild(principal) if (
            created
            or owners.get(str(principal.user_id)) != self._authorization_signature(principal)
        ) else {
            "state": "ready", "indexed": None,
            "projection_version": SEMANTIC_ABSTRACTION_VERSION,
        }
        result["queue"] = self.process_pending(principal)
        return result

    def search(
        self,
        principal: Any,
        text: str,
        *,
        authorized_space_ids: Iterable[str] = (),
        scope: str | None = None,
        form: str | None = None,
        status: str | None = None,
        space_id: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        query = _normalize(text)
        if not query or not self.configured:
            return []
        self.ensure_ready(principal)
        vector = self._ollama([query], principal=principal)[0]
        must: list[dict[str, Any]] = [
            {"key": "privacy", "match": {"value": "normal"}},
            {"key": "status", "match": {"any": ["active", "working"]}},
        ]
        for key, value in (
            ("scope", scope), ("form", form), ("status", status),
            ("space_id", space_id), ("project_id", project_id),
            ("conversation_id", conversation_id),
        ):
            if value:
                must.append({"key": key, "match": {"value": value}})
        spaces = self._current_space_ids(principal, authorized_space_ids)
        should: list[dict[str, Any]] = [
            {
                "must": [
                    {"key": "owner_user_id", "match": {"value": principal.user_id}},
                    {"is_empty": {"key": "space_id"}},
                ]
            }
        ]
        if spaces:
            should.append({"key": "space_id", "match": {"any": spaces}})
        assert self.config is not None
        payload = self._qdrant(
            "POST", f"/collections/{self.config.collection}/points/query",
            {
                "query": vector, "filter": {"must": must, "should": should},
                "params": {"hnsw_ef": 128, "exact": False},
                "limit": max(1, min(limit, 500)),
                "with_payload": True, "with_vector": False,
            },
            timeout=30.0,
        ) or {}
        points = (payload.get("result") or {}).get("points")
        if not isinstance(points, list):
            raise SemanticProjectionError("Qdrant returned an invalid query contract.")
        rows: list[dict[str, Any]] = []
        for point in points:
            source = dict(point.get("payload") or {}) if isinstance(point, dict) else {}
            memory_id = str(source.get("memory_id") or "")
            if not memory_id or source.get("privacy") != "normal":
                continue
            owner_ok = (
                source.get("owner_user_id") == principal.user_id
                and not str(source.get("space_id") or "")
            )
            space_ok = str(source.get("space_id") or "") in spaces
            if not (owner_ok or space_ok):
                raise SemanticProjectionError("Qdrant returned a point outside the hard authorization filter.")
            try:
                record = self.fabric.get(principal, memory_id)
            except Exception:
                continue
            if str(getattr(record.privacy, "value", record.privacy)) != "normal":
                continue
            current_status = str(getattr(record.status, "value", record.status))
            if current_status not in {"active", "working"}:
                continue
            current_scope = str(getattr(record.scope, "value", record.scope))
            current_form = str(getattr(record.form, "value", record.form))
            current_space = str(record.space_id) if record.space_id else None
            current_project = _linked_id(record, "project")
            current_conversation = _linked_id(record, "conversation")
            if source.get("owner_user_id") != record.owner_user_id or (
                str(source.get("space_id") or "") or None
            ) != current_space:
                continue
            if scope and current_scope != scope:
                continue
            if form and current_form != form:
                continue
            if status and current_status != status:
                continue
            if space_id and current_space != space_id:
                continue
            if project_id and current_project != project_id:
                continue
            if conversation_id and current_conversation != conversation_id:
                continue
            rows.append({
                "candidate_id": memory_id,
                "semantic_score": max(0.0, min(1.0, float(point.get("score") or 0.0))),
                "record": record,
                "projection_payload_owner_user_id": str(source.get("owner_user_id") or ""),
                "projection_payload_space_id": str(source.get("space_id") or "") or None,
            })
        return rows

    def health(self, *, probe: bool = True) -> dict[str, Any]:
        pending = failed = 0
        try:
            database = self.paths.memory_database_path
            if database.exists() and database.is_file() and not database.is_symlink():
                import sqlite3

                uri = f"file:{database.as_posix()}?mode=ro"
                canonical = sqlite3.connect(uri, uri=True, timeout=1.0)
            else:
                canonical = None
            if canonical is not None:
                pending = int(canonical.execute(
                    "SELECT COUNT(*) FROM memory_jobs WHERE state='pending' AND job_kind LIKE 'semantic_%'"
                ).fetchone()[0])
                failed = int(canonical.execute(
                    "SELECT COUNT(*) FROM memory_jobs WHERE state='failed' AND job_kind LIKE 'semantic_%'"
                ).fetchone()[0])
                canonical.close()
        except Exception:
            pass
        base = {
            "abstraction_version": SEMANTIC_ABSTRACTION_VERSION,
            "benchmark_version": SEMANTIC_BENCHMARK_VERSION,
            "promotion_decision": SEMANTIC_PROMOTION_DECISION,
            "production_retrieval": "sqlite_fts5_plus_normal_memory_qwen_qdrant_rrf",
            "profile": "semantic_local_optional", "configured": self.configured,
            "qwen_model": EMBEDDING_MODEL, "qwen_dimension": EMBEDDING_DIMENSION,
            "embedding_device_policy": "compute_governor_gpu_when_earned_cpu_fallback_no_permanent_reservation",
            "semantic_task_mrr_relative_gain_percent": 28.14,
            "qdrant_server_loopback_only": True, "qdrant_authenticated": True,
            "qdrant_derived_rebuildable": True,
            "canonical_memory_authority": "sqlite_memory_fabric",
            "private_strategy": "authenticated_ephemeral_lexical_no_persistent_vector",
            "sealed_vectors_persisted": False, "private_vectors_persisted": False,
            "shared_vector_identity": "source_owner_plus_space_acl",
            "pending_jobs": pending, "failed_jobs": failed, "raw_path_exposed": False,
        }
        if not self.configured:
            return {**base, "state": "optional_not_installed", "server_ready": False, "model_ready": False}
        if not probe:
            return {**base, "state": "configured_unprobed", "server_ready": None, "model_ready": None}
        try:
            self.ensure_collection()
            assert self.config is not None
            collection = self._qdrant("GET", f"/collections/{self.config.collection}", timeout=3.0) or {}
            info = collection.get("result") or {}
            with urlopen(Request(self.config.ollama_url + "/api/tags", method="GET"), timeout=1.0) as response:
                tags = self._decode(response)
            names = {str(item.get("name") or "") for item in tags.get("models", []) if isinstance(item, dict)}
            model_ready = self.config.model in names
            return {
                **base, "state": "ready" if model_ready and failed == 0 else "degraded",
                "server_ready": True, "model_ready": model_ready,
                "indexed_normal_records": int(info.get("points_count") or 0),
                "indexed_vectors": int(info.get("indexed_vectors_count") or 0),
                "collection_status": str(info.get("status") or "unknown"),
            }
        except Exception:
            return {**base, "state": "degraded", "server_ready": False, "model_ready": False}


def semantic_projection_health(
    *, paths: ElysiaPaths | None = None, repository: MemoryRepository | None = None,
    fabric: MemoryFabricService | None = None, probe: bool = True,
) -> dict[str, Any]:
    try:
        return SemanticMemoryProjection(paths=paths, repository=repository, fabric=fabric).health(probe=probe)
    except Exception:
        return {
            "state": "degraded", "abstraction_version": SEMANTIC_ABSTRACTION_VERSION,
            "benchmark_version": SEMANTIC_BENCHMARK_VERSION,
            "promotion_decision": SEMANTIC_PROMOTION_DECISION,
            "configured": False, "server_ready": False, "model_ready": False,
            "qdrant_server_loopback_only": True, "qdrant_derived_rebuildable": True,
            "private_vectors_persisted": False, "sealed_vectors_persisted": False,
            "raw_path_exposed": False,
        }


__all__ = (
    "COLLECTION", "EMBEDDING_DIMENSION", "EMBEDDING_MODEL", "PREPROCESSING_VERSION",
    "SEMANTIC_ABSTRACTION_VERSION", "SEMANTIC_BENCHMARK_VERSION",
    "SEMANTIC_PROMOTION_DECISION", "SemanticMemoryProjection",
    "SemanticProjectionConfig", "SemanticProjectionError",
    "SemanticProjectionUnavailable", "semantic_projection_health",
)
