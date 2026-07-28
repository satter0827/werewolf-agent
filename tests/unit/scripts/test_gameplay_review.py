"""Gameplay review証拠の再現性と秘匿性。"""

from scripts.review.gameplay import generate_gameplay_evidence


def test_gameplay_evidence_is_reproducible_and_public_only() -> None:
    first = generate_gameplay_evidence(seed=17)
    second = generate_gameplay_evidence(seed=17)

    assert first == second
    assert first["outcome"]["winner"]
    assert first["operations"]
    assert first["public_timeline"]
    assert all("target_id" not in operation for operation in first["operations"])
    assert all(event["visibility"] == "public" for event in first["public_timeline"])
