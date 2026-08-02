"""決定的なapplication coreの性能観測。"""

from __future__ import annotations

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from werewolf_agent.setup import checksum_payload


@pytest.mark.benchmark
def test_canonical_payload_checksum(benchmark: BenchmarkFixture) -> None:
    """Replay整合性に使うcanonical checksumの処理時間を観測する。"""
    payload = {
        "game_id": "game-1",
        "version": 42,
        "players": [
            {"id": f"p{index}", "alive": index % 3 != 0, "role": None} for index in range(15)
        ],
        "timeline": [
            {"version": index, "kind": "speech", "utterance": "状況を確認します。"}
            for index in range(100)
        ],
    }

    digest = benchmark(checksum_payload, payload)

    assert len(digest) == 64
    assert digest == checksum_payload(payload)
