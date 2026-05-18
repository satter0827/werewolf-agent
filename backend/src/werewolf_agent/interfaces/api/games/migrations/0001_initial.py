"""Create game run persistence tables."""

from __future__ import annotations

import uuid
from typing import ClassVar

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: ClassVar[list[tuple[str, str]]] = []

    operations: ClassVar[list[object]] = [
        migrations.CreateModel(
            name="GameRun",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("status", models.CharField(default="running", max_length=24)),
                ("phase", models.CharField(max_length=32)),
                ("day", models.PositiveIntegerField(default=1)),
                ("seed", models.IntegerField(blank=True, null=True)),
                ("config", models.JSONField(default=dict)),
                ("public_state", models.JSONField(default=dict)),
                ("private_state", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="GameEventRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("sequence", models.PositiveIntegerField()),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("visibility", models.CharField(default="public", max_length=24)),
                ("phase", models.CharField(blank=True, max_length=32, null=True)),
                ("day", models.PositiveIntegerField(blank=True, null=True)),
                ("actor_id", models.CharField(blank=True, max_length=128, null=True)),
                ("event_type", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="games.gamerun",
                    ),
                ),
            ],
            options={
                "ordering": ["run_id", "sequence"],
            },
        ),
        migrations.AddConstraint(
            model_name="gameeventrecord",
            constraint=models.UniqueConstraint(
                fields=("run", "sequence"),
                name="games_event_record_run_sequence_unique",
            ),
        ),
    ]
