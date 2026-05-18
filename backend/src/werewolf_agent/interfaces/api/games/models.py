"""Database models for the games API app."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.utils import timezone


class GameRun(models.Model):
    """Persisted game run owned by the API server."""

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=24, default=STATUS_RUNNING)
    phase = models.CharField(max_length=32)
    day = models.PositiveIntegerField(default=1)
    seed = models.IntegerField(null=True, blank=True)
    config = models.JSONField(default=dict)
    public_state = models.JSONField(default=dict)
    private_state = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"GameRun({self.id}, {self.status}/{self.phase})"


class GameEventRecord(models.Model):
    """Persisted event stream record for one game run."""

    VISIBILITY_PUBLIC = "public"
    VISIBILITY_PLAYER_PRIVATE = "player_private"
    VISIBILITY_DEBUG = "debug"

    run = models.ForeignKey(GameRun, related_name="events", on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()
    event_id = models.UUIDField(default=uuid.uuid4, editable=False)
    visibility = models.CharField(max_length=24, default=VISIBILITY_PUBLIC)
    phase = models.CharField(max_length=32, null=True, blank=True)
    day = models.PositiveIntegerField(null=True, blank=True)
    actor_id = models.CharField(max_length=128, null=True, blank=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering: ClassVar[list[str]] = ["run_id", "sequence"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["run", "sequence"],
                name="games_event_record_run_sequence_unique",
            )
        ]

    def __str__(self) -> str:
        return f"GameEventRecord({self.run_id}, {self.sequence}, {self.event_type})"
