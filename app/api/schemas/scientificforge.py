"""Typed contracts for bounded local ScientificForge jobs.

ScientificForge is a fixed-operation scientific-compute organ. These schemas
do not grant arbitrary Python, shell, notebook, network, package-install,
source-mutation, or external-system authority.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from app.api.schemas.common import (
    ApprovalState,
    ElysiaSchemaModel,
    LocalityState,
)
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
)


SCIENTIFICFORGE_PROTOCOL_VERSION = "scientificforge-v0.1"


class ScientificOperation(str, Enum):
    """Initial fixed-operation ScientificForge registry."""

    DESCRIPTIVE_STATS = "descriptive_stats"
    CORRELATION_MATRIX = "correlation_matrix"
    BOOTSTRAP_MEAN_CI = "bootstrap_mean_ci"
    MATRIX_MULTIPLY = "matrix_multiply"
    MONTE_CARLO_NORMAL = "monte_carlo_normal"


class ScientificExecutionRequest(ElysiaSchemaModel):
    """One bounded scientific-compute request."""

    operation: ScientificOperation

    request_id: str | None = Field(
        default=None,
        max_length=160,
    )

    source_file_id: str | None = Field(
        default=None,
        max_length=160,
        description=(
            "Existing Elysia attached-file identifier. "
            "ScientificForge resolves the private ingest copy itself."
        ),
    )

    columns: list[str] = Field(
        default_factory=list,
        max_length=16,
        description="Bounded selected columns for table-backed operations.",
    )

    values: list[float] = Field(
        default_factory=list,
        max_length=100_000,
        description="Bounded inline numeric vector for supported operations.",
    )

    matrix_a: list[list[float]] = Field(
        default_factory=list,
        max_length=64,
    )

    matrix_b: list[list[float]] = Field(
        default_factory=list,
        max_length=64,
    )

    seed: int | None = Field(
        default=None,
        ge=0,
        le=4_294_967_295,
        description=(
            "Explicit deterministic RNG seed. "
            "Required by stochastic operations."
        ),
    )

    bootstrap_samples: int = Field(
        default=2_000,
        ge=100,
        le=10_000,
    )

    confidence_level: float = Field(
        default=0.95,
        gt=0.0,
        lt=1.0,
    )

    monte_carlo_samples: int = Field(
        default=10_000,
        ge=100,
        le=100_000,
    )

    distribution_mean: float = 0.0

    distribution_stddev: float = Field(
        default=1.0,
        gt=0.0,
    )


class ScientificSourceReceipt(ElysiaSchemaModel):
    """Public-safe identity receipt for one verified scientific input."""

    source_file_id: str
    source_file_name: str
    source_file_kind: str
    source_sha256: str
    size_bytes: int = Field(ge=0)

    trust_zone: str = "user_selected_private_ingest_copy"
    source_copy_verified: bool = True

    locality: LocalityState = LocalityState.LOCAL
    memory_posture: str = "not_memory"

    raw_path_exposed: bool = False


class ScientificProvenance(ElysiaSchemaModel):
    """Deterministic scientific result provenance."""

    protocol_version: str = SCIENTIFICFORGE_PROTOCOL_VERSION
    operation: str

    source_sha256: str | None = None
    parameter_sha256: str
    result_sha256: str

    seed: int | None = None
    deterministic: bool = True

    engine_versions: dict[str, str] = Field(
        default_factory=dict,
    )

    network_access_used: bool = False
    source_mutated: bool = False
    arbitrary_python_used: bool = False
    shell_used: bool = False
    package_install_used: bool = False


class ScientificExecutionResult(ElysiaSchemaModel):
    """Result contract for one governed ScientificForge job."""

    ok: bool = False

    status: ExecutionStatus = ExecutionStatus.FAILED

    tool_kind: ExecutionToolKind = ExecutionToolKind.SCIENTIFIC_FORGE

    operation: str

    request_id: str | None = Field(
        default=None,
        description=(
            "Optional caller correlation identifier. "
            "This is not a cancellation or execution-authority key."
        ),
    )

    job_id: str | None = Field(
        default=None,
        description=(
            "ScientificForge-owned execution identity and control-plane key."
        ),
    )

    source: ScientificSourceReceipt | None = None

    seed_used: int | None = None

    compute_device: str = "cpu"
    compute_governed: bool = False

    result: dict[str, Any] = Field(default_factory=dict)

    provenance: ScientificProvenance | None = None

    locality: LocalityState = LocalityState.LOCAL
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED

    network_access_used: bool = False
    source_mutated: bool = False
    arbitrary_python_used: bool = False
    shell_used: bool = False

    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    execution_note: str = (
        "Bounded local ScientificForge execution. "
        "No arbitrary Python, shell, notebook, network, package installation, "
        "source mutation, external mutation, or memory promotion is implied."
    )


__all__ = (
    "SCIENTIFICFORGE_PROTOCOL_VERSION",
    "ScientificExecutionRequest",
    "ScientificExecutionResult",
    "ScientificOperation",
    "ScientificProvenance",
    "ScientificSourceReceipt",
)
