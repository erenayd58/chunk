"""Character folds: the one thing a lexical index and its queries must share.

A BM25 index is only as good as the agreement between how a document was
tokenised and how the question is. The fold below is applied *identically* at
index time and at search time, which is what lets a query typed without
Turkish diacritics -- ``ogretim`` for ``öğretim`` -- match the text that has
them. It is a reversible character map and deliberately not stemming: nothing
here decides that two different words are one.

It lives in :mod:`amsc.retrieval` rather than beside a benchmark because three
callers need to agree on it and only one of them is research:

* the frozen retrieval benchmark, whose recorded numbers were produced with it;
* the Viewer's per-arm index, so a question asked of a live document is
  tokenised exactly as the benchmark tokenised a frozen one;
* the console, which reproduces the same fold in its production BM25 retriever.

Two functions rather than one flag, and a mapping rather than a branch, so a
configuration can *name* its fold (``fold: turkish_diacritics_v1``) and a run
can record which one it used.
"""

from __future__ import annotations

from typing import Callable, Mapping

#: Reproduces ``chat_rag.components.retriever.bm25_only_retriever``'s
#: production fold. Both dotted and dotless ``i`` fold to ``i``, so the two
#: Turkish letters English has one of stop being two tokens.
_TURKISH_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i", "i": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
        "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
    }
)


def fold_turkish(text: str) -> str:
    return text.translate(_TURKISH_FOLD).lower()


def identity_fold(text: str) -> str:
    return text


#: Every fold a configuration may name, by the id that goes into a run record.
FOLDS: Mapping[str, Callable[[str], str]] = {
    "turkish_diacritics_v1": fold_turkish,
    "none": identity_fold,
}
