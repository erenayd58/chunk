"""The Deep Analysis safety contract, on the real corpora.

Fixtures prove the selector does the right thing on shapes chosen to exercise
it. Only the corpora prove it does no harm across 214 and 226 real sections --
including the one cross-section rejoin the frozen walk performs, which a
per-section selector has to restore deliberately.

Pins here are *properties*, not numbers: Standard is reproduced byte for byte,
coverage is unchanged, the hard cap holds, and no section comes out with a
smell type Standard did not have. The measured improvement is reported by
``amsc.boundary_quality`` and lives in artifacts, not in an assertion, so a
better selector is never blocked by this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amsc import boundary_quality as bq
from amsc import deep_analysis as da
from amsc.io import load_jsonl_units
from amsc.structural_chunker import RENDER_SEPARATOR, _render, _sections
from amsc.structural_chunker import chunk_units as structural_chunk_units
from amsc.tokenization import TiktokenTokenCounter

CORPORA = ("data/kkb-2024.units.v3.jsonl", "data/kkb-2022.units.v3.jsonl")
CONFIG = da.DeepConfig()


def _load(path: str):
    file = Path(path)
    if not file.is_file():
        pytest.skip(f"{path} is not present in this clone")
    return load_jsonl_units(file)


@pytest.fixture(scope="module")
def counter():
    return TiktokenTokenCounter("cl100k_base")


def _standard(units, counter):
    return structural_chunk_units(
        units,
        counter=counter,
        min_tokens=CONFIG.min_tokens,
        target_tokens=CONFIG.target_tokens,
        soft_max_tokens=CONFIG.soft_max_tokens,
        hard_max_tokens=CONFIG.hard_max_tokens,
        respect_semantic_roles=CONFIG.respect_semantic_roles,
    )


@pytest.mark.parametrize("path", CORPORA)
def test_standard_groups_plus_the_rejoin_reproduce_the_frozen_chunker(path, counter):
    """Byte for byte, including the cross-section merges (1 on 2024, 2 on 2022)."""
    units = _load(path)
    expected = _standard(units, counter)
    assembled = []
    for index, section in enumerate(
        _sections(units, counter, CONFIG.hard_max_tokens, CONFIG.respect_semantic_roles)
    ):
        for group in da.standard_groups(section, counter=counter, config=CONFIG):
            assembled.append(
                (section.heading, [list(block) for block in group],
                 tuple(section.section_path), index, False)
            )
    joined = da._rejoin_across_sections(assembled, counter=counter, config=CONFIG)
    assert len(joined) == len(expected)
    for chunk, (heading, group, _path, _index, _moved) in zip(expected, joined):
        text = RENDER_SEPARATOR.join(_render(heading, block) for block in group)
        assert chunk["text"] == text
        assert chunk["unit_ids"] == [piece.unit_id for block in group for piece in block]


@pytest.mark.parametrize("path", CORPORA)
def test_deep_preserves_coverage_order_and_the_hard_cap(path, counter):
    units = _load(path)
    standard = _standard(units, counter)
    rows, audit = da.chunk_units(units, counter=counter, config=CONFIG)
    assert [i for row in rows for i in row["unit_ids"]] == [
        i for chunk in standard for i in chunk["unit_ids"]
    ]
    assert all(row["token_count"] <= CONFIG.hard_max_tokens for row in rows)
    assert audit["verdicts"][bq.VERDICT_WORSE] == 0


@pytest.mark.parametrize("path", CORPORA)
def test_no_section_regresses_and_smells_fall(path, counter):
    units = _load(path)
    standard = _standard(units, counter)
    rows, _ = da.chunk_units(units, counter=counter, config=CONFIG)
    report = bq.compare(units, standard, rows, counter=counter, config=CONFIG.quality())
    assert report["structural_regression_count"] == 0
    assert report["verdicts_tiered"][bq.VERDICT_WORSE] == 0
    smells = lambda totals: sum(totals[key] for key in bq.SMELL_TYPES)  # noqa: E731
    assert smells(report["totals"]["deep"]) < smells(report["totals"]["standard"])
    for key in bq.SMELL_TYPES:
        assert report["totals"]["deep"][key] <= report["totals"]["standard"][key]


@pytest.mark.parametrize("path", CORPORA)
def test_the_run_is_reproducible(path, counter):
    units = _load(path)
    first, first_audit = da.chunk_units(units, counter=counter, config=CONFIG)
    second, second_audit = da.chunk_units(units, counter=counter, config=CONFIG)
    assert first == second
    assert first_audit == second_audit
