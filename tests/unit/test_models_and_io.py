from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from amsc.io import load_jsonl_units
from amsc.models import RawDocumentUnit


def test_heading_requires_heading_level() -> None:
    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(
            {
                "document_id": "doc",
                "unit_id": "h1",
                "order": 1,
                "text": "Heading",
                "type": "heading",
            }
        )


def test_non_heading_rejects_heading_level() -> None:
    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(
            {
                "document_id": "doc",
                "unit_id": "p1",
                "order": 1,
                "text": "Paragraph",
                "type": "paragraph",
                "heading_level": 2,
            }
        )


@pytest.mark.parametrize("field", ["unit_id", "order"])
def test_jsonl_rejects_duplicate_identity(tmp_path, field: str) -> None:
    rows = [
        {
            "document_id": "doc",
            "unit_id": "p1",
            "order": 1,
            "text": "One",
            "type": "paragraph",
        },
        {
            "document_id": "doc",
            "unit_id": "p2",
            "order": 2,
            "text": "Two",
            "type": "paragraph",
        },
    ]
    rows[1][field] = rows[0][field]
    path = tmp_path / "input.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        load_jsonl_units(path)


def test_jsonl_rejects_out_of_order_units(tmp_path) -> None:
    path = tmp_path / "input.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"document_id":"d","unit_id":"a","order":2,"text":"A","type":"paragraph"}',
                '{"document_id":"d","unit_id":"b","order":1,"text":"B","type":"paragraph"}',
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="increasing order"):
        load_jsonl_units(path)


def test_sample_fixture_is_valid() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    assert len(units) == 4
    assert units[0].heading_level == 2

