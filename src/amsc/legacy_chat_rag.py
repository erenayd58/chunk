from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable, Sequence

from .models import RawDocumentUnit, UnitType
from .tokenization import TokenCounter


_PUBLIC_SOURCE_COMMIT = "3fbe307c4d68eedcfb9cdaf14a73ca34eab14bcf"
_SPECIAL_CHARACTER_FILTER = re.compile(r"[^\w\s.,!?;:()\-'\"]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class LegacyChatRAGProfile:
    """Pinned public chat_rag code-default profile.

    This is not a claim about KKB's inaccessible production agentic chunker.  It is
    a compatibility profile for the public repository at ``source_commit``.
    """

    source_repository: str = "https://github.com/MurselTasgin/chat_rag"
    source_commit: str = _PUBLIC_SOURCE_COMMIT
    profile_id: str = "public_code_defaults_on_frozen_canonical_v1"
    chunk_size_words: int = 300
    chunk_overlap_words: int = 60
    min_chunk_size_words: int = 50
    sentence_tokenizer: str = "deterministic_punctuation_span_v1"
    use_semantic_segmentation: bool = True
    use_embedding_segmentation: bool = False

    def __post_init__(self) -> None:
        if self.chunk_size_words < 1:
            raise ValueError("legacy chunk_size_words must be positive")
        if self.chunk_overlap_words < 0:
            raise ValueError("legacy chunk_overlap_words cannot be negative")
        if self.chunk_overlap_words >= self.chunk_size_words:
            raise ValueError("legacy overlap must be smaller than chunk size")
        if self.min_chunk_size_words < 1:
            raise ValueError("legacy min_chunk_size_words must be positive")
        if self.sentence_tokenizer != "deterministic_punctuation_span_v1":
            raise ValueError("Unsupported legacy compatibility sentence tokenizer")
        if self.use_embedding_segmentation:
            raise ValueError(
                "The frozen public code-default profile has embedding segmentation disabled"
            )


@dataclass(frozen=True)
class LegacyChunkRecord:
    chunk_id: str
    text: str
    unit_ids: tuple[str, ...]
    content_unit_ids: tuple[str, ...]
    pages: tuple[int, ...]
    token_count: int
    section_heading_unit_id: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": "kkb-2024",
            "text": self.text,
            "token_count": self.token_count,
            "unit_ids": list(self.unit_ids),
            "content_unit_ids": list(self.content_unit_ids),
            "pages": list(self.pages),
            "legacy_profile": "public_code_defaults_on_frozen_canonical_v1",
            "section_heading_unit_id": self.section_heading_unit_id,
        }


@dataclass(frozen=True)
class _MappedSentence:
    text: str
    unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class _CanonicalSection:
    heading: RawDocumentUnit | None
    content: tuple[RawDocumentUnit, ...]


class LegacyChatRAGCanonicalAdapter:
    """Run public chat_rag sentence packing on the frozen canonical units.

    Parser behavior is intentionally held constant: canonical heading units define
    sections and canonical content units provide text/provenance.  Public chat_rag's
    generated ``Title/Document/Section`` retrieval header is disabled because Phase
    4 forbids contextualization.  The original heading text is retained once as raw
    source content in the first emitted chunk of its section.

    The public implementation calls TextTiling *after* ``clean_text`` collapses all
    whitespace.  Consequently paragraph breaks are absent and TextTiling falls back
    to the whole section.  The adapter records that compatibility fact and proceeds
    directly to the public sentence-packing behavior.
    """

    def __init__(
        self,
        profile: LegacyChatRAGProfile,
        token_counter: TokenCounter,
        *,
        sentence_span_tokenizer: Callable[[str], Iterable[tuple[int, int]]] | None = None,
    ) -> None:
        self.profile = profile
        self.token_counter = token_counter
        self._sentence_span_tokenizer = (
            sentence_span_tokenizer or _load_public_sentence_span_tokenizer()
        )

    @property
    def compatibility_notes(self) -> tuple[str, ...]:
        return (
            "canonical headings replace the public repository's parser heuristic",
            "generated Title/Document/Section retrieval headers are disabled",
            "TextTiling is configured but deterministically falls back after whitespace collapse",
            "public sentence packing, word limits, overlap, and short-tail dropping are retained",
            "dependency-free punctuation spans replace public NLTK English Punkt sentence tokenization",
            "this comparator is not the inaccessible KKB production agentic chunker",
        )

    def build(self, units: Sequence[RawDocumentUnit]) -> list[LegacyChunkRecord]:
        if not units:
            raise ValueError("legacy adapter requires canonical units")
        raw_by_id = {unit.unit_id: unit for unit in units}
        packed: list[tuple[str, tuple[str, ...], str | None]] = []

        for section in _canonical_sections(units):
            text, spans = _clean_section(section.content)
            if not text:
                continue
            sentences = self._mapped_sentences(text, spans)
            section_chunks = self._pack_sentences(sentences)
            for section_chunk_index, (content, content_ids) in enumerate(section_chunks):
                heading_id = section.heading.unit_id if section.heading else None
                if section_chunk_index == 0 and section.heading is not None:
                    rendered = f"{section.heading.text}\n\n{content}"
                    unit_ids = _unique((section.heading.unit_id, *content_ids))
                else:
                    rendered = content
                    unit_ids = content_ids
                packed.append((rendered, unit_ids, heading_id))

        if not packed:
            content_units = [unit for unit in units if unit.type != UnitType.HEADING]
            text, _ = _clean_section(content_units)
            if text:
                packed.append((text, tuple(unit.unit_id for unit in content_units), None))

        records: list[LegacyChunkRecord] = []
        for index, (text, unit_ids, heading_id) in enumerate(packed, start=1):
            content_ids = tuple(
                unit_id
                for unit_id in unit_ids
                if raw_by_id[unit_id].type != UnitType.HEADING
            )
            pages = tuple(
                sorted(
                    {
                        raw_by_id[unit_id].source.page
                        for unit_id in unit_ids
                        if raw_by_id[unit_id].source.page is not None
                    }
                )
            )
            records.append(
                LegacyChunkRecord(
                    chunk_id=f"legacy-chat-rag:chunk-{index:04d}",
                    text=text,
                    unit_ids=unit_ids,
                    content_unit_ids=content_ids,
                    pages=pages,
                    token_count=self.token_counter.count(text),
                    section_heading_unit_id=heading_id,
                )
            )
        return records

    def _mapped_sentences(
        self,
        text: str,
        unit_spans: Sequence[tuple[int, int, str]],
    ) -> list[_MappedSentence]:
        sentences: list[_MappedSentence] = []
        for start, end in self._sentence_span_tokenizer(text):
            sentence = text[start:end].strip()
            if not sentence:
                continue
            ids = tuple(
                unit_id
                for unit_start, unit_end, unit_id in unit_spans
                if start < unit_end and end > unit_start
            )
            if not ids:
                raise AssertionError("Legacy sentence lost canonical provenance")
            sentences.append(_MappedSentence(sentence, _unique(ids)))
        if not sentences and text:
            ids = _unique(unit_id for _, _, unit_id in unit_spans)
            sentences.append(_MappedSentence(text, ids))
        return sentences

    def _pack_sentences(
        self, sentences: Sequence[_MappedSentence]
    ) -> list[tuple[str, tuple[str, ...]]]:
        chunks: list[tuple[str, tuple[str, ...]]] = []
        current: list[_MappedSentence] = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence.text.split())
            if (
                current_length + sentence_length > self.profile.chunk_size_words
                and current
            ):
                chunk_text = " ".join(item.text for item in current)
                if len(chunk_text.split()) >= self.profile.min_chunk_size_words:
                    chunks.append(
                        (
                            chunk_text,
                            _unique(
                                unit_id
                                for item in current
                                for unit_id in item.unit_ids
                            ),
                        )
                    )

                overlap: list[_MappedSentence] = []
                overlap_length = 0
                for item in reversed(current):
                    item_length = len(item.text.split())
                    if (
                        overlap_length + item_length
                        <= self.profile.chunk_overlap_words
                    ):
                        overlap.insert(0, item)
                        overlap_length += item_length
                    else:
                        break
                current = overlap
                current_length = overlap_length

            current.append(sentence)
            current_length += sentence_length

        if current:
            chunk_text = " ".join(item.text for item in current)
            if len(chunk_text.split()) >= self.profile.min_chunk_size_words:
                chunks.append(
                    (
                        chunk_text,
                        _unique(
                            unit_id
                            for item in current
                            for unit_id in item.unit_ids
                        ),
                    )
                )
        return chunks


def clean_legacy_text(text: str) -> str:
    collapsed = _WHITESPACE.sub(" ", text)
    return _SPECIAL_CHARACTER_FILTER.sub("", collapsed).strip()


def _canonical_sections(
    units: Sequence[RawDocumentUnit],
) -> list[_CanonicalSection]:
    sections: list[_CanonicalSection] = []
    heading: RawDocumentUnit | None = None
    content: list[RawDocumentUnit] = []
    for unit in units:
        if unit.type == UnitType.HEADING:
            if content:
                sections.append(_CanonicalSection(heading, tuple(content)))
                content = []
            heading = unit
        else:
            content.append(unit)
    if content:
        sections.append(_CanonicalSection(heading, tuple(content)))
    return sections


def _clean_section(
    units: Sequence[RawDocumentUnit],
) -> tuple[str, tuple[tuple[int, int, str], ...]]:
    pieces: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for unit in units:
        cleaned = clean_legacy_text(unit.text)
        if not cleaned:
            continue
        if pieces:
            cursor += 1
        start = cursor
        pieces.append(cleaned)
        cursor += len(cleaned)
        spans.append((start, cursor, unit.unit_id))
    return " ".join(pieces), tuple(spans)


def _load_public_sentence_span_tokenizer() -> Callable[[str], Iterable[tuple[int, int]]]:
    sentence = re.compile(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)", re.UNICODE)

    def spans(text: str) -> Iterable[tuple[int, int]]:
        for match in sentence.finditer(text):
            if match.group(0).strip():
                yield match.span()

    return spans


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
