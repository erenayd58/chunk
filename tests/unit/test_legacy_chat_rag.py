from __future__ import annotations

import re

from amsc.legacy_chat_rag import (
    LegacyChatRAGCanonicalAdapter,
    LegacyChatRAGProfile,
    clean_legacy_text,
)
from amsc.models import RawDocumentUnit


class _WordCounter:
    counter_id = "words:test"

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str, max_tokens: int) -> list[str]:
        words = text.split()
        return [" ".join(words[i : i + max_tokens]) for i in range(0, len(words), max_tokens)]


def _spans(text: str):
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        if match.group(0).strip():
            yield match.span()


def _unit(unit_id: str, order: int, text: str, unit_type: str = "paragraph"):
    return RawDocumentUnit.model_validate(
        {
            "document_id": "kkb-2024",
            "unit_id": unit_id,
            "order": order,
            "text": text,
            "type": unit_type,
            "heading_level": 2 if unit_type == "heading" else None,
            "source": {"page": order},
        }
    )


def test_public_sentence_packing_overlap_and_canonical_provenance() -> None:
    units = [
        _unit("h1", 1, "Başlık", "heading"),
        _unit("p1", 2, "bir iki üç. dört beş altı."),
        _unit("p2", 3, "yedi sekiz dokuz. on onbir oniki."),
    ]
    profile = LegacyChatRAGProfile(
        chunk_size_words=6,
        chunk_overlap_words=3,
        min_chunk_size_words=3,
    )
    chunks = LegacyChatRAGCanonicalAdapter(
        profile, _WordCounter(), sentence_span_tokenizer=_spans
    ).build(units)

    assert len(chunks) == 3
    assert chunks[0].text.startswith("Başlık\n\n")
    assert chunks[0].unit_ids == ("h1", "p1")
    assert chunks[1].unit_ids == ("p1", "p2")
    assert chunks[2].unit_ids == ("p2",)
    assert all(chunk.pages for chunk in chunks)


def test_short_section_tail_is_dropped_like_public_chunker() -> None:
    units = [
        _unit("h1", 1, "Bir", "heading"),
        _unit("p1", 2, "çok kısa."),
        _unit("h2", 3, "İki", "heading"),
        _unit("p2", 4, "bu bölüm yeterince uzun bir cümle içerir."),
    ]
    profile = LegacyChatRAGProfile(
        chunk_size_words=20, chunk_overlap_words=2, min_chunk_size_words=5
    )
    chunks = LegacyChatRAGCanonicalAdapter(
        profile, _WordCounter(), sentence_span_tokenizer=_spans
    ).build(units)

    assert len(chunks) == 1
    assert "p1" not in chunks[0].unit_ids
    assert chunks[0].unit_ids == ("h2", "p2")


def test_legacy_cleaning_matches_public_character_and_whitespace_policy() -> None:
    assert clean_legacy_text(" A\n\nB | **C** € ") == "A B  C " .strip()


def test_legacy_notes_do_not_claim_kbb_production_equivalence() -> None:
    adapter = LegacyChatRAGCanonicalAdapter(
        LegacyChatRAGProfile(), _WordCounter(), sentence_span_tokenizer=_spans
    )
    assert any("not the inaccessible KKB production" in note for note in adapter.compatibility_notes)

