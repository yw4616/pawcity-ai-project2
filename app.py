"""PawCity HTTP server: data explorer + LLM-backed /chat endpoint.

Use python app.py locally or run as the Cloud Run container entrypoint.
The Google Cloud project and ADC provide Vertex AI Gemini access; no API key is used.
"""
from __future__ import annotations

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pawcity.pipeline import read_csv
from pawcity.research_agent import PawCityResearch

ROOT = Path(__file__).resolve().parent
MAX_BODY = 16_384


def snapshot():
    summary_path = ROOT / "data/processed/zip_summary.csv"
    quality_path = ROOT / "data/processed/data_quality_report.json"
    provenance_path = ROOT / "data/metadata/query_log.json"
    rows = read_csv(summary_path) if summary_path.exists() else []
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {}
    return rows, quality, provenance


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route in {"/", "/index.html"}:
            self._send(200, "text/html; charset=utf-8", (ROOT / "static/index.html").read_bytes())
            return
        rows, quality, provenance = snapshot()
        if route == "/health":
            self._json(200, {"ok": True, "project": "pawcity-ai", "model_provider": "vertex_ai", "model_configured": bool(os.getenv("GOOGLE_CLOUD_PROJECT")),
                             "data_sources_ok": sum(s.get("status") == "ok" for s in provenance.values()),
                             "phase": "deep_research"})
        elif route == "/api/summary":
            self._json(200, {"rows": rows, "quality": quality, "sources": provenance,
                             "model_configured": bool(os.getenv("GOOGLE_CLOUD_PROJECT"))})
        elif route == "/api/quality":
            self._json(200, quality)
        elif route == "/api/provenance":
            self._json(200, provenance)
        elif route == "/api/sample-questions":
            self._json(200, {"questions": [
                "Compare ZIP 10001 and ZIP 10002 using dog runs, license periods, 2025 barking complaints and bite reports.",
                "Which NYC ZIP areas have no recorded dog runs despite many license periods?",
                "Which ZIP codes have the most recorded dog runs, and what can't this tell us?",
                "Can these sources prove which NYC ZIP is safest for dogs? Explain the evidence limits."]})
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/chat":
            self._json(404, {"error": "Not found"})
            return
        session_id = str(uuid.uuid4())
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                self._json(413, {"error": "Request must contain at most 16 KB of JSON"})
                return
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            question = payload.get("message", payload.get("question", ""))
            if not isinstance(question, str) or len(question.strip()) < 1 or len(question) > 3000:
                raise ValueError("message must be a nonempty string of at most 3000 characters")
            supplied_session_id = payload.get("session_id")
            if supplied_session_id is not None and (not isinstance(supplied_session_id, str) or
                                                     not 0 < len(supplied_session_id.strip()) <= 128):
                raise ValueError("session_id must be a nonempty string of at most 128 characters")
            session_id = supplied_session_id or str(uuid.uuid4())
            if not os.getenv("GOOGLE_CLOUD_PROJECT"):
                error = "Live research is not configured: set GOOGLE_CLOUD_PROJECT and grant the runtime service account Vertex AI access."
                self._json(503, {"error": error, "response": error, "session_id": session_id,
                                 "tool_calls": [], "citations": []})
                return
            report = PawCityResearch(ROOT, max_turns=int(os.environ.get("PAWCITY_MAX_TURNS", "2"))).run(question)
            # Preserve Project 1's response, session_id and tool_calls contract.
            # Additional citation/trace fields are retained for the PawCity frontend.
            result = report.to_dict()
            result["session_id"] = session_id
            self._json(200, result)
        except (ValueError, json.JSONDecodeError) as err:
            error = str(err)
            self._json(400, {"error": error, "response": error,
                             "session_id": session_id, "tool_calls": []})
        except (RuntimeError, FileNotFoundError):
            # Avoid exposing vendor API errors or partial credentials to public clients.
            error = "Research is temporarily unavailable. Please retry after checking model access and data files."
            self._json(503, {"error": error, "response": error,
                             "session_id": session_id, "tool_calls": []})
        except Exception:
            # Do not leak API keys, stack traces or internal request bodies to clients.
            error = "Research failed unexpectedly. Check the server logs."
            self._json(500, {"error": error, "response": error,
                             "session_id": session_id, "tool_calls": []})
            raise

    def _send(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status, obj):
        content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", content)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"PawCity AI is serving on http://127.0.0.1:{port} (live model configured: {bool(os.getenv('GOOGLE_CLOUD_PROJECT'))})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
