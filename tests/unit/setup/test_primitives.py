"""Headless setup primitivesの公開契約を検査する."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from werewolf_agent.setup import (
    PlayerGenerationDefinition,
    PlayerIdentityDefinition,
    PrivateStrategyDefinition,
    PublicPersonaDefinition,
    checksum_payload,
    generate_players,
    namespace_seed,
)


def _definition() -> PlayerGenerationDefinition:
    return PlayerGenerationDefinition(
        identities=(
            PlayerIdentityDefinition("Alice", 20, 30, "female"),
            PlayerIdentityDefinition("Bob", 31, 40, "male"),
        ),
        public_personas=(PublicPersonaDefinition("calm", "brief"),),
        private_strategies=(PrivateStrategyDefinition("analytic", "low", "claims"),),
    )


def test_same_definition_and_seed_generate_the_same_roster() -> None:
    """同じ入力から同じ完全rosterとchecksumを生成する."""
    first = generate_players(_definition(), player_count=2, seed=41)
    second = generate_players(_definition(), player_count=2, seed=41)

    assert first == second
    assert checksum_payload([player.private_payload() for player in first]) == checksum_payload(
        [player.private_payload() for player in second]
    )


def test_seed_namespaces_are_stable_and_isolated() -> None:
    """用途別seedを安定して分離する."""
    assert namespace_seed(41, "roster") == namespace_seed(41, "roster")
    assert namespace_seed(41, "roster") != namespace_seed(41, "role_assignment")


def test_setup_values_are_immutable_and_validate_at_construction() -> None:
    """外部利用者による直接構築でも不正値を拒否する."""
    identity = PlayerIdentityDefinition("Alice", 20, 30, "female")
    with pytest.raises(FrozenInstanceError):
        identity.name = "Changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="ages must satisfy"):
        PlayerIdentityDefinition("Alice", 30, 20, "female")
    with pytest.raises(ValueError, match="risk_tolerance"):
        PrivateStrategyDefinition("analytic", "unknown", "claims")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive integer"):
        generate_players(_definition(), player_count=0, seed=41)
