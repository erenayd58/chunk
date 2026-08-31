"""The RAG chat, held to its contract with fake providers.

No network, no model: a bag-of-words embedder that is deterministic and
actually ranks, plus an answer double that returns the JSON contract. The
guarantees under test are the ones the Sorgu tab relies on -- one retriever
for every arm, an expansion that never crosses a section, stable source
labels, a readable failure when the answer model is down, and no secret in
any response.
"""

from __future__ import annotations

import hashlib
import io
import json
import http.client
import re

import numpy as np
import pytest

from amsc import rag_answer, rag_chat, rag_context, rag_embeddings, rag_index
from amsc.viewer_server import console_document, console_prepare, console_workspace, make_server, serve_in_thread


class BagOfWordsEmbedder:
    """Deterministic hashed bag-of-words; cosine follows word overlap."""

    model_id = "test/bow@1"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                out[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class JsonAnswerer:
    model_id = "test/answer@1"

    def __init__(self, reply=None, fail=False):
        self.reply = reply
        self.fail = fail
        self.prompts = []

    def chat(self, system, user):
        self.prompts.append((system, user))
        if self.fail:
            raise RuntimeError("endpoint down")
        labels = re.findall(r"\[(S\d+)\]", user)
        reply = self.reply or json.dumps(
            {"answer": f"Üye sayısı 197'dir [{labels[0]}].", "sources_used": [labels[0]], "sufficient": True}
        )
        return reply, {"prompt_tokens": 10, "completion_tokens": 5}


def rows():
    return [
        {"chunk_id": "doc:s-chunk-0001", "text": "**1. GIRIS**\n\nKurum hakkinda genel bilgi.", "unit_ids": ["p-1"],
         "token_count": 8, "pages": [1], "section_paths": [["**1. GIRIS**"]], "heading": "**1. GIRIS**"},
        {"chunk_id": "doc:s-chunk-0002", "text": "**2. UYELER**\n\nUye sayisi 197 olarak gerceklesti.", "unit_ids": ["p-2"],
         "token_count": 9, "pages": [2], "section_paths": [["**2. UYELER**"]], "heading": "**2. UYELER**"},
        {"chunk_id": "doc:s-chunk-0003", "text": "**2. UYELER**\n\nBankalar ve faktoring sirketleri uyedir.", "unit_ids": ["p-3"],
         "token_count": 9, "pages": [2], "section_paths": [["**2. UYELER**"]], "heading": "**2. UYELER**"},
        {"chunk_id": "doc:s-chunk-0004", "text": "**3. MALI**\n\nNet kar artti.", "unit_ids": ["p-4"],
         "token_count": 6, "pages": [3], "section_paths": [["**3. MALI**"]], "heading": "**3. MALI**"},
    ]


def make_catalog(tmp_path):
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("".join(json.dumps(r) + "\n" for r in rows()), encoding="utf-8")
    units = tmp_path / "units.jsonl"
    units.write_text("", encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({
        "documents": {
            "doc": {
                "label": "Doc",
                "units": "units.jsonl",
                "canonical_sha256": "x",
                "arms": {
                    "structure-only": {"kind": "structure_first", "chunks": "chunks.jsonl"},
                    "agentic": {"kind": "deep_analysis", "chunks": "chunks.jsonl"},
                },
            }
        }
    }), encoding="utf-8")
    return rag_chat.Catalog.load(catalog, root=tmp_path)


def engine(tmp_path, *, answerer=None, dense=True):
    embedder = rag_embeddings.CachedEmbeddings(BagOfWordsEmbedder(), tmp_path / "cache") if dense else None
    return rag_chat.ChatEngine(
        catalog=make_catalog(tmp_path),
        retrieval=rag_index.RetrievalSettings(top_k=3),
        context=rag_context.ContextSettings(max_context_tokens=40, expansion_budget=30),
        embedder=embedder,
        answerer=answerer,
    )


# --- retrieval -------------------------------------------------------------


def test_the_index_ranks_by_the_question_and_caches_embeddings(tmp_path):
    provider = BagOfWordsEmbedder()
    embedder = rag_embeddings.CachedEmbeddings(provider, tmp_path / "cache")
    index = rag_index.index_rows("agentic", "deep_analysis", rows(), settings=rag_index.RetrievalSettings(), embedder=embedder)
    hits = index.search("uye sayisi kac", top_k=2)
    assert hits[0].chunk_id == "doc:s-chunk-0002"
    assert index.stats.embedding_cache_misses == 4 and index.stats.dense
    again = rag_index.index_rows("agentic", "deep_analysis", rows(), settings=rag_index.RetrievalSettings(), embedder=embedder)
    assert again.stats.embedding_cache_hits == 4 and again.stats.embedding_cache_misses == 0
    assert provider.calls == 2  # 1 for the documents, 1 for the query


def test_lexical_only_retrieval_works_without_an_embedder():
    index = rag_index.index_rows("structure-only", "structure_first", rows(), settings=rag_index.RetrievalSettings(), embedder=None)
    hits = index.search("faktoring sirketleri", top_k=1)
    assert hits[0].chunk_id == "doc:s-chunk-0003" and not index.dense


def test_context_expansion_stays_inside_the_section_and_labels_are_stable():
    index = rag_index.index_rows("structure-only", "structure_first", rows(), settings=rag_index.RetrievalSettings(), embedder=None)
    hits = index.search("uye sayisi 197", top_k=1)
    context = rag_context.assemble_context(
        hits, index.chunks, kind="structure_first",
        settings=rag_context.ContextSettings(max_context_tokens=100, expansion_budget=100),
    )
    ids = [block.chunk_id for block in context.blocks]
    # chunk 3 continues chunk 2 (same heading, same path) -> pulled in; chunk 4 is another section -> not.
    assert ids == ["doc:s-chunk-0002", "doc:s-chunk-0003"]
    assert [block.label for block in context.blocks] == ["S1", "S2"]
    assert [block.role for block in context.blocks] == ["hit", "neighbour_after"]
    assert "[S1]" in context.render() and "[S2]" in context.render()


def test_the_budget_is_never_overspent_and_drops_are_recorded():
    index = rag_index.index_rows("structure-only", "structure_first", rows(), settings=rag_index.RetrievalSettings(), embedder=None)
    hits = index.search("uye bankalar kurum", top_k=4)
    context = rag_context.assemble_context(
        hits, index.chunks, kind="structure_first",
        settings=rag_context.ContextSettings(max_context_tokens=12, expansion_budget=12),
    )
    assert context.total_tokens <= 12
    assert context.dropped and all(d["reason"] in ("budget", "expansion_budget") for d in context.dropped)


# --- answers ----------------------------------------------------------------


def test_parse_answer_handles_json_and_plain_text():
    parsed = rag_answer.parse_answer('{"answer": "197 [S1]", "sources_used": ["S1", "S9"], "sufficient": true}', ["S1", "S2"])
    assert parsed.parsed and parsed.sources_used == ["S1"] and parsed.sufficient is True
    plain = rag_answer.parse_answer("Cevap: 197 üye [S2].", ["S1", "S2"])
    assert not plain.parsed and plain.sources_used == ["S2"] and plain.sufficient is None
    assert rag_answer.parse_answer(None, ["S1"]).answer == ""


def test_ask_returns_a_grounded_answer_with_source_cards(tmp_path):
    answerer = JsonAnswerer()
    response = engine(tmp_path, answerer=answerer).ask("doc", "agentic", "uye sayisi kac")
    assert response["status"] == "ok"
    assert response["answer"]["sufficient"] is True
    assert response["sources"][0]["used"] is True and response["sources"][0]["label"] == "S1"
    assert response["sources"][0]["chunk_id"] == "doc:s-chunk-0002"
    assert response["sources"][0]["text"].startswith("**2. UYELER**")
    assert response["models"] == {"embedding": "test/bow@1", "answer": "test/answer@1"}
    system, user = answerer.prompts[0]
    assert "[S1]" in user and "KAYNAKLAR" in user
    assert "token" not in system.lower().replace("tokens", "")  # no size talk in the answer prompt
    assert "OPENROUTER" not in json.dumps(response) and "sk-" not in json.dumps(response)


def test_an_answer_model_failure_still_returns_the_sources(tmp_path):
    response = engine(tmp_path, answerer=JsonAnswerer(fail=True)).ask("doc", "agentic", "uye sayisi")
    assert response["status"] == "answer_error" and response["answer"] is None
    assert response["sources"] and "ulaşılamadı" in response["error"]


def test_no_answer_model_is_an_explicit_status(tmp_path):
    response = engine(tmp_path, answerer=None).ask("doc", "agentic", "uye sayisi")
    assert response["status"] == "no_answer_model" and response["sources"]


def test_bad_requests_are_value_errors(tmp_path):
    e = engine(tmp_path)
    with pytest.raises(ValueError):
        e.ask("nope", "agentic", "soru")
    with pytest.raises(ValueError):
        e.ask("doc", "nope", "soru")
    with pytest.raises(ValueError):
        e.ask("doc", "agentic", "   ")


def test_compare_runs_the_same_question_over_every_arm(tmp_path):
    result = engine(tmp_path, answerer=JsonAnswerer()).compare("doc", "uye sayisi kac")
    assert set(result["arms"]) == {"structure-only", "agentic"}
    assert result["unit_overlap_with_other_arms"]["agentic"] == 1.0


# --- the server ---------------------------------------------------------------


def test_the_server_serves_the_viewer_and_the_api(tmp_path):
    viewer = tmp_path / "index.html"
    viewer.write_text("<html><body>viewer</body></html>", encoding="utf-8")
    server = make_server(engine(tmp_path, answerer=JsonAnswerer()), viewer, port=0, quiet=True)
    serve_in_thread(server)
    host, port = server.server_address[:2]
    try:
        conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.request("GET", "/")
        assert b"viewer" in conn.getresponse().read()
        conn.request("GET", "/api/health")
        health = json.loads(conn.getresponse().read())
        assert health["ok"] and "doc" in health["documents"]
        conn.request("POST", "/api/chat", body=json.dumps({"doc": "doc", "arm": "agentic", "question": "uye sayisi"}),
                     headers={"Content-Type": "application/json"})
        chat = json.loads(conn.getresponse().read())
        assert chat["status"] == "ok" and chat["sources"]
        conn.request("POST", "/api/chat", body=json.dumps({"doc": "zzz", "arm": "agentic", "question": "x"}),
                     headers={"Content-Type": "application/json"})
        bad = conn.getresponse()
        assert bad.status == 400 and "unknown document" in json.loads(bad.read())["error"]
        conn.request("GET", "/api/chunk?doc=doc&arm=agentic&chunk_id=doc:s-chunk-0002")
        chunk = json.loads(conn.getresponse().read())
        assert chunk["chunk_id"] == "doc:s-chunk-0002" and "197" in chunk["text"]
    finally:
        server.shutdown()
        server.server_close()


# --- the workspace bridge to the RAG console -----------------------------------
#
# The viewer page must never have to know the console's address: it asks its own
# origin, and this process does the cross-service call. A console that is down
# is an answer the page can render, not an error that blanks the panel.


def test_the_workspace_route_relays_the_console(tmp_path, monkeypatch):
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Response(json.dumps({
            "success": True,
            "knowledge_bases": [{"kb_id": "kb1", "name": "kkb-final", "documents": []}],
            "totals": {"knowledge_bases": 1, "documents": 0, "chunks": 0},
        }).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    viewer = tmp_path / "index.html"
    viewer.write_text("<html><body>viewer</body></html>", encoding="utf-8")
    server = make_server(engine(tmp_path, answerer=JsonAnswerer()), viewer, port=0, quiet=True,
                         console_url="http://127.0.0.1:5005")
    serve_in_thread(server)
    host, port = server.server_address[:2]
    try:
        conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.request("GET", "/api/workspace")
        payload = json.loads(conn.getresponse().read())
    finally:
        server.shutdown()
        server.server_close()
    assert payload["connected"] is True
    assert payload["knowledge_bases"][0]["name"] == "kkb-final"
    assert seen["url"] == "http://127.0.0.1:5005/api/demo/workspace"
    assert seen["timeout"] <= 5, "a panel refresh must not stall the page"


def test_a_stopped_console_is_an_answer_not_an_error(monkeypatch):
    import urllib.error
    import urllib.request

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    payload = console_workspace("http://127.0.0.1:5005")
    assert payload["connected"] is False and payload["configured"] is True
    assert "refused" in payload["reason"]


def test_no_console_address_means_no_call():
    assert console_workspace("") == {
        "connected": False, "configured": False, "url": "", "reason": "not configured",
    }


def test_a_live_document_payload_is_relayed_from_the_console(monkeypatch):
    """The console builds a live document's payload from its own ingest; this
    process moves JSON and neither parses a document nor calls a model."""
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["timeout"] = timeout
        return _Response(json.dumps({
            "success": True, "doc_id": "upload_1_pdf",
            "payload": {"label": "a.pdf", "arms": {"structure-only": {}, "agentic": {}}},
        }).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    payload = console_document("http://127.0.0.1:5005", "upload_1_pdf")
    assert payload["connected"] is True
    assert sorted(payload["payload"]["arms"]) == ["agentic", "structure-only"]
    assert seen["url"] == "http://127.0.0.1:5005/api/demo/viewer-analysis/upload_1_pdf/payload"
    assert seen["timeout"] > 5, "a whole document's payload needs longer than a status poll"


def test_asking_for_an_unbuilt_document_returns_its_state_not_an_exception(monkeypatch):
    import urllib.error
    import urllib.request

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", None,
            io.BytesIO(json.dumps({"success": False, "error": "no viewer payload",
                                   "state": {"status": "pending"}}).encode()),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    answer = console_document("http://127.0.0.1:5005", "upload_1_pdf")
    assert answer["connected"] is True and answer["http_status"] == 404
    assert answer["state"] == {"status": "pending"}


def test_preparing_a_document_is_a_post_to_the_console(monkeypatch):
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        return _Response(json.dumps({"success": True, "state": {"status": "pending"}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    answer = console_prepare("http://127.0.0.1:5005", "upload 1/pdf")
    assert answer["connected"] is True and answer["state"]["status"] == "pending"
    assert seen["method"] == "POST"
    assert seen["url"] == "http://127.0.0.1:5005/api/demo/viewer-analysis/upload%201%2Fpdf"


def test_the_refresh_can_ask_the_console_to_prepare(monkeypatch):
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        return _Response(json.dumps({"success": True, "knowledge_bases": [], "totals": {}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    console_workspace("http://127.0.0.1:5005")
    assert seen["url"].endswith("/api/demo/workspace")
    console_workspace("http://127.0.0.1:5005", prepare=True)
    assert seen["url"].endswith("/api/demo/workspace?prepare=1")


# --- live documents relayed from the console -----------------------------------
#
# A document uploaded to the RAG console is not in this process's frozen
# catalog. Its rows are handed over instead of read, and everything downstream
# -- indexing, retrieval, the source cards -- must not be able to tell the
# difference. The one thing that is different is that rows can be replaced.


def test_a_live_document_is_indexed_from_the_rows_it_was_handed(tmp_path):
    """No chunks.jsonl on this machine, and retrieval still ranks."""
    e = engine(tmp_path)
    registered = e.register_live(
        "upload_1_pdf", "a.pdf", {"agentic": {"kind": "deep_analysis", "rows": rows()}}
    )
    assert registered["arms"]["agentic"]["chunk_count"] == len(rows())

    spec = e.catalog.documents["upload_1_pdf"].arms["agentic"]
    assert spec.chunks is None, "a live arm is indexed from memory, not from a path"
    assert e.catalog.describe()["upload_1_pdf"]["live"] is True
    assert e.catalog.describe()["doc"]["live"] is False

    response = e.retrieve("upload_1_pdf", "agentic", "uye sayisi kac")
    assert response["hits"][0]["chunk_id"] == "doc:s-chunk-0002"
    assert response["arm_kind"] == "deep_analysis"
    assert response["sources"], "a live document gets the same source cards as a frozen one"

    with pytest.raises(ValueError):
        e.register_live("empty_pdf", "b.pdf", {"agentic": {"kind": "deep_analysis", "rows": []}})


def test_re_registering_a_document_drops_the_index_it_answered_from(tmp_path):
    """Re-analysed means re-chunked: the old index must not survive it."""
    e = engine(tmp_path)
    e.register_live("upload_1_pdf", "a.pdf", {"agentic": {"kind": "deep_analysis", "rows": rows()}})
    assert e.retrieve("upload_1_pdf", "agentic", "uye sayisi kac")["hits"][0]["chunk_id"] == "doc:s-chunk-0002"
    assert ("upload_1_pdf", "agentic") in e._indexes
    e.notes["upload_1_pdf/agentic"] = "dense retrieval unavailable; BM25 only"

    rebuilt = [
        {"chunk_id": "doc:v2-chunk-0001", "text": "**2. UYELER**\n\nUye sayisi 212 olarak gerceklesti.",
         "unit_ids": ["p-2"], "token_count": 9, "pages": [2],
         "section_paths": [["**2. UYELER**"]], "heading": "**2. UYELER**"},
    ]
    e.register_live("upload_1_pdf", "a.pdf", {"agentic": {"kind": "deep_analysis", "rows": rebuilt}})

    assert ("upload_1_pdf", "agentic") not in e._indexes
    assert "upload_1_pdf/agentic" not in e.notes
    assert e.catalog.documents["doc"].arms, "another document's registration is untouched"

    again = e.retrieve("upload_1_pdf", "agentic", "uye sayisi kac")
    assert [hit["chunk_id"] for hit in again["hits"]] == ["doc:v2-chunk-0001"]
    assert "212" in again["sources"][0]["text"]
