"""The shared token budget, as the engines behind the shipped methods take it.

Named with a leading underscore, so :mod:`amsc.chunking.discovery` skips it:
a plugin directory may hold a helper, and a helper is not a method. This one
exists because Standard and Hybrid pass the same four numbers to two different
engines, and neither should restate them.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The shared budget's four numbers. Every method runs to the same ones, so a
#: comparison is about where the boundaries fall and nothing else.
BUDGET_KEYS = ("min_tokens", "target_tokens", "soft_max_tokens", "hard_max_tokens")


def budget_kwargs(budget: Mapping[str, Any]) -> dict[str, int]:
    return {name: int(budget[name]) for name in BUDGET_KEYS if name in budget}
