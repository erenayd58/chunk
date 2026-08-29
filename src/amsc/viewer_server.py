"""A small local server that gives the Viewer v2 HTML a live RAG backend.

    GET  /                      the viewer (built by amsc.viewer_v2)
    GET  /api/health            models, documents, arms, index state
    GET  /api/docs              the catalog
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
import sys
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from .rag_chat import Catalog, ChatEngine, load_config

MAX_BODY_BYTES = 64 * 1024


class ViewerHandler(BaseHTTPRequestHandler):
    engine: ChatEngine  # set by make_server
    viewer_path: Path
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
    engine: ChatEngine, viewer_path: Path, *, host: str = "127.0.0.1", port: int = 8765, quiet: bool = False
) -> ThreadingHTTPServer:
    handler = type("BoundViewerHandler", (ViewerHandler,), {"engine": engine, "viewer_path": Path(viewer_path)})
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
    server = make_server(engine, args.viewer, host=args.host, port=args.port)
    print(
        json.dumps(
            {
                "serving": f"http://{args.host}:{args.port}/",
                "viewer": str(args.viewer),
                "catalog": str(catalog_path),
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
