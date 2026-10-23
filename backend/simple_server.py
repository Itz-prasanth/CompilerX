"""Dependency-free HTTP server exposing the API (used when FastAPI is not installed)."""
from __future__ import annotations
import json, logging, mimetypes, os, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .logging_setup import setup
from .service import Service, ApiError, ROOT

log = logging.getLogger("compilerx.http")
MAX_BODY = 1_000_000


def make_handler(svc: Service):
    GET = {"/api/health": lambda q: svc.health(), "/api/languages": lambda q: svc.languages(), "/api/samples": lambda q: svc.samples(),
           "/api/model/status": lambda q: svc.model_status(), "/api/benchmark/results": lambda q: svc.benchmark_results(),
           "/api/benchmark/status": lambda q: svc.benchmark_status((q.get("job") or [None])[0]),
           "/api/history": lambda q: svc.history(int((q.get("limit") or [50])[0]))}
    POST = {"/api/compile": svc.compile, "/api/run": svc.run, "/api/diagnose": svc.diagnose, "/api/patch/validate": svc.validate_patch,
            "/api/patch/apply": svc.apply_patch, "/api/benchmark/run": svc.benchmark_start, "/api/counterfactual": svc.counterfactual}

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            log.info(fmt % a)

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "http://localhost:5173"); self.end_headers(); self.wfile.write(b)

        def do_OPTIONS(self):
            self.send_response(204)
            for k, v in (("Access-Control-Allow-Origin", "http://localhost:5173"), ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type")):
                self.send_header(k, v)
            self.end_headers()

        def _guard(self, fn):
            try:
                self._send(200, fn())
            except ApiError as e:
                self._send(e.status, {"error": e.message})
            except Exception as e:
                log.error("unhandled: %s", traceback.format_exc())
                self._send(500, {"error": f"internal error: {type(e).__name__}"})

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in GET:
                return self._guard(lambda: GET[u.path](parse_qs(u.query)))
            dist = os.path.join(ROOT, "frontend", "dist")
            p = os.path.normpath(os.path.join(dist, u.path.lstrip("/") or "index.html"))
            if p.startswith(dist) and os.path.isfile(p):
                data = open(p, "rb").read(); self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "application/octet-stream"); self.send_header("Content-Length", str(len(data)))
                self.end_headers(); return self.wfile.write(data)
            self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urlparse(self.path)
            if u.path not in POST:
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "request body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "invalid JSON"})
            self._guard(lambda: POST[u.path](body))
    return H


def main():
    setup()
    host = os.environ.get("COMPILERX_HOST", "127.0.0.1"); port = int(os.environ.get("COMPILERX_PORT", "8000"))
    svc = Service()
    log.info("serving on http://%s:%d (stdlib server)", host, port)
    ThreadingHTTPServer((host, port), make_handler(svc)).serve_forever()


if __name__ == "__main__":
    main()
