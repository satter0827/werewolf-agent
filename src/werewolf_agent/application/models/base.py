"""Shared validation policy for application DTOs."""

from pydantic import BaseModel, ConfigDict


class ApplicationModel(BaseModel):
    """Base model for application commands, results, and records."""

    model_config = ConfigDict(extra="forbid", frozen=True)
