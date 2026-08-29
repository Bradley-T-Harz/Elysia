"""Emergency-stop API contracts."""

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class EmergencyStopRequest(ElysiaSchemaModel):
    reason: str = Field(default="Operator emergency stop", min_length=3, max_length=300)


class EmergencyResetRequest(ElysiaSchemaModel):
    acknowledge_safe_restart: bool = True


__all__ = ("EmergencyResetRequest", "EmergencyStopRequest")
