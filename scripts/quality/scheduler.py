"""個別gate selectorを既存gate定義へ解決する。"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.quality.models import Gate
from scripts.quality.profiles import expand_selectors


def select_stages(
    all_stages: Sequence[Sequence[Gate]], selectors: Sequence[str]
) -> list[list[Gate]]:
    """Profile catalogから選択したgateの実行stageを返す。"""
    catalog = {gate.name: gate for stage in all_stages for gate in stage}
    names = expand_selectors(selectors, set(catalog))
    pending = list(names)
    while pending:
        name = pending.pop()
        for dependency in catalog[name].dependencies:
            if dependency not in catalog:
                raise ValueError(f"{name}の依存gateが未定義です: {dependency}")
            if dependency not in names:
                names.add(dependency)
                pending.append(dependency)
    dependencies = {name: set(catalog[name].dependencies) for name in names}
    remaining = set(names)
    completed: set[str] = set()
    stages: list[list[Gate]] = []
    while remaining:
        ready = sorted(name for name in remaining if dependencies[name].issubset(completed))
        if not ready:
            raise ValueError("品質gateの依存関係が循環しています。")
        batches: list[list[Gate]] = []
        batch_resources: list[set[str]] = []
        for name in ready:
            gate = catalog[name]
            resources = set(gate.exclusive_resources)
            for index, occupied in enumerate(batch_resources):
                if resources.isdisjoint(occupied):
                    batches[index].append(gate)
                    occupied.update(resources)
                    break
            else:
                batches.append([gate])
                batch_resources.append(resources)
        stages.extend(batches)
        completed.update(ready)
        remaining.difference_update(ready)
    return stages


__all__ = ["select_stages"]
