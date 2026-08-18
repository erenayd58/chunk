from __future__ import annotations

import pytest
from pydantic import ValidationError

from amsc.config import V1Config
from amsc.tokenization import TiktokenTokenCounter


def test_v1_rejects_future_version_fields() -> None:
    payload = V1Config().model_dump(mode="python")
    payload["threshold"] = {"mad_lambda": 1.5}
    with pytest.raises(ValidationError, match="threshold"):
        V1Config.model_validate(payload)


def test_default_parameters_are_explicitly_marked_unoptimized() -> None:
    config = V1Config()
    assert config.algorithm.tuning_status == "poc_initial_not_optimized"
    assert config.token_counter.cap_semantics == "configured_poc_counter_only"


def test_tiktoken_counter_splits_according_to_configured_encoding() -> None:
    counter = TiktokenTokenCounter("cl100k_base")
    text = "Türkçe bir örnek metin ve birkaç ek sözcük"
    pieces = counter.split(text, max_tokens=3)
    assert pieces
    assert all(counter.count(piece) <= 3 for piece in pieces)
    assert "".join(pieces) == text
    assert counter.counter_id.startswith("tiktoken:cl100k_base@")
