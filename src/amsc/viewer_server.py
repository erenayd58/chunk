"""A small local server that gives the Viewer v2 HTML a live RAG backend.

    GET  /                      the viewer (built by amsc.viewer_v2)
    GET  /api/health            models, documents, arms, index state
    GET  /api/docs              the catalog
    GET  /api/workspace         the RAG console's live knowledge bases
    GET  /api/live-document     one console document's viewer payload
    POST /api/live-prepare      ask the console to build one document's analysis
    GET  /api/chunk?doc&arm&chunk_id
    POST /api/retrieve          {doc, arm, question, top_k?}
    POST /api/chat              {doc, arm, question, top_k?}
    POST /api/compare           {doc, question, arms?, top_k?, answers?}

The HTML works without this server -- Sunum, Debug and Benchmark are
offline, and Sorgu falls back to the frozen gold-query view -- and gains the
chat when served from here. Keys never reach the page: the browser talks to
this process, this process talks to the providers, and only the providers'
model ids are ever sent back. Standard library only, so the demo has no
extra dependency to install.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from .rag_chat import Catalog, ChatEngine, load_config

MAX_BODY_BYTES = 64 * 1024
DEFAULT_CONSOLE_URL = "http://127.0.0.1:5005"
CONSOLE_TIMEOUT_SECONDS = 2.5
#: A document payload carries a whole document's text, not a status line.
CONSOLE_PAYLOAD_TIMEOUT_SECONDS = 30.0


def _console_call(
    console_url: str,
    path: str,
    *,
    method: str = "GET",
    timeout: float = CONSOLE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """One call to the RAG console, made by this process rather than the page.

    The viewer page asks its own origin for everything, so the demo needs no
    CORS grant and no console address in the browser. An unreachable console
    is an answer ("connected: false"), not an error, because the page has to
    stay usable with the console stopped.
    """
    if not console_url:
        return {"connected": False, "configured": False, "url": "", "reason": "not configured"}
    request = urllib.request.Request(console_url.rstrip("/") + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            payload = {}
        return {
            "connected": True,
            "configured": True,
            "url": console_url,
            "reason": str(payload.get("error") or f"HTTP {error.code}"),
            "state": payload.get("state"),
            "http_status": error.code,
        }
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "connected": False,
            "configured": True,
            "url": console_url,
            "reason": f"{type(error).__name__}: {error}",
        }
    if not isinstance(payload, dict) or not payload.get("success"):
        reason = (payload or {}).get("error") if isinstance(payload, dict) else "unexpected payload"
        return {"connected": False, "configured": True, "url": console_url, "reason": str(reason)}
    payload.pop("success", None)
    return {"connected": True, "configured": True, "url": console_url, **payload}


def console_workspace(
    console_url: str, timeout: float = CONSOLE_TIMEOUT_SECONDS, *, prepare: bool = False
) -> dict[str, Any]:
    """The console's live knowledge bases, and where each document's viewer
    analysis got to. ``prepare`` additionally asks it to queue the missing
    ones -- queuing only; the console packages them on its own worker."""
    return _console_call(
        console_url, "/api/demo/workspace" + ("?prepare=1" if prepare else ""), timeout=timeout
    )


def console_document(console_url: str, doc_id: str) -> dict[str, Any]:
    """One live document's finished viewer payload, relayed from the console.

    Built there from that document's own ingest, so this process neither
    parses a PDF nor calls a model; it moves JSON. The payload carries a
    document's full text, so it gets a longer timeout than a status poll.
    """
    quoted = urllib.parse.quote(str(doc_id), safe="")
    return _console_call(
        console_url, f"/api/demo/viewer-analysis/{quoted}/payload", timeout=CONSOLE_PAYLOAD_TIMEOUT_SECONDS
    )


def console_prepare(console_url: str, doc_id: str) -> dict[str, Any]:
    """Ask the console to build (or rebuild) one document's viewer analysis."""
    quoted = urllib.parse.quote(str(doc_id), safe="")
    return _console_call(console_url, f"/api/demo/viewer-analysis/{quoted}", method="POST")


class ViewerHandler(BaseHTTPRequestHandler):
    engine: ChatEngine  # set by make_server
    viewer_path: Path
    console_url: str = ""
    server_version = "amsc-viewer/2"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if getattr(self.server, "quiet", False):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    # -- helpers --------------------------------------------------------------

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path: Path) -> None:
        if not path.is_file():
            self._send_json({"error": f"viewer not found at {path}"}, HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    # -- routes -----------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            if route in ("/", "/index.html"):
                self._send_html(self.viewer_path)
            elif route == "/api/health":
                self._send_json(self.engine.health())
            elif route == "/api/docs":
                self._send_json(self.engine.catalog.describe())
            elif route == "/api/workspace":
                self._send_json(
                    console_workspace(self.console_url, prepare=query.get("prepare") in ("1", "true"))
                )
            elif route == "/api/live-document":
                self._send_json(console_document(self.console_url, query["doc"]))
            elif route == "/api/chunk":
                self._send_json(self.engine.chunk(query["doc"], query["arm"], query["chunk_id"]))
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (KeyError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # pragma: no cover - defensive
            self._send_json({"error": f"internal error: {type(error).__name__}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        route = urllib.parse.urlsplit(self.path).path
        try:
            body = self._read_json()
            question = str(body.get("question") or "")
            top_k = body.get("top_k")
            top_k = int(top_k) if top_k else None
            if route == "/api/retrieve":
                result = self.engine.retrieve(str(body.get("doc")), str(body.get("arm")), question, top_k=top_k)
                result.pop("_context", None)
                self._send_json(result)
            elif route == "/api/chat":
                self._send_json(
                    self.engine.ask(str(body.get("doc")), str(body.get("arm")), question, top_k=top_k)
                )
            elif route == "/api/live-prepare":
                self._send_json(console_prepare(self.console_url, str(body.get("doc"))))
            elif route == "/api/compare":
                arms = body.get("arms")
                self._send_json(
                    self.engine.compare(
                        str(body.get("doc")),
                        question,
                        arms=[str(a) for a in arms] if isinstance(arms, list) else None,
                        top_k=top_k,
                        answers=bool(body.get("answers", True)),
                    )
                )
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
        except Exception as error:  # pragma: no cover - defensive
            self._send_json({"error": f"internal error: {type(error).__name__}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def make_server(
    engine: ChatEngine,
    viewer_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    quiet: bool = False,
    console_url: str | None = None,
) -> ThreadingHTTPServer:
    if console_url is None:
        console_url = os.environ.get("AMSC_CONSOLE_URL", DEFAULT_CONSOLE_URL)
    handler = type(
        "BoundViewerHandler",
        (ViewerHandler,),
        {"engine": engine, "viewer_path": Path(viewer_path), "console_url": console_url},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.quiet = quiet  # type: ignore[attr-defined]
    server.daemon_threads = True
    return server


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.viewer_server",
        description="Serve the Viewer v2 HTML with a live RAG chat backend",
    )
    parser.add_argument("--viewer", type=Path, default=Path("artifacts/viewer-v2/index.html"))
    parser.add_argument("--catalog", type=Path, help="defaults to catalog.json beside the viewer")
    parser.add_argument("--config", type=Path, default=Path("configs/rag-poc.yaml"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--console-url",
        default=os.environ.get("AMSC_CONSOLE_URL", DEFAULT_CONSOLE_URL),
        help="RAG console address the workspace panel reads (empty disables the panel)",
    )
    parser.add_argument("--warm", action="store_true", help="build every index before serving")
    parser.add_argument("--lexical", action="store_true", help="BM25 only, no embedding provider")
    parser.add_argument("--no-answer", action="store_true", help="retrieval only, no answer model")
    args = parser.parse_args(argv)

    catalog_path = args.catalog or args.viewer.with_name("catalog.json")
    catalog = Catalog.load(catalog_path, root=args.root)
    engine = ChatEngine.from_config(
        catalog, load_config(args.config), root=args.root,
        dense=not args.lexical, answers=not args.no_answer,
    )
    if args.warm:
        report = engine.warm()
        print(json.dumps({"warmed": report}, ensure_ascii=False, indent=1))
    server = make_server(engine, args.viewer, host=args.host, port=args.port, console_url=args.console_url)
    print(
        json.dumps(
            {
                "serving": f"http://{args.host}:{args.port}/",
                "viewer": str(args.viewer),
                "catalog": str(catalog_path),
                "console_url": args.console_url,
                "embedding_model": engine.embedder.model_id if engine.embedder else None,
                "answer_model": engine.answerer.model_id if engine.answerer else None,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
