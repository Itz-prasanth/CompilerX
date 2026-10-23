import json, os, tempfile, threading, urllib.request, urllib.error, re
from http.server import ThreadingHTTPServer
from tests.helpers import INVALID, ROOT
from backend.service import Service
from backend.simple_server import make_handler

_S = {}


def _server():
    if "url" not in _S:
        svc = Service(db_path=os.path.join(tempfile.mkdtemp(), "t.db"))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _S.update(url=f"http://127.0.0.1:{srv.server_address[1]}", srv=srv, svc=svc)
    return _S["url"]


def call(method, path, body=None, raw=None):
    req = urllib.request.Request(_server() + path, data=raw if raw is not None else (json.dumps(body).encode() if body is not None else None), method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_languages_samples():
    c, h = call("GET", "/api/health"); assert c == 200 and h["all_toolchains_available"] and not h["execution"]["enabled"]
    c, l = call("GET", "/api/languages"); assert {x["id"] for x in l["languages"]} == {"c", "cpp", "java", "python"}
    c, s = call("GET", "/api/samples"); assert c == 200 and len(s["samples"]) >= 20


def test_compile_and_diagnose_roundtrip_and_history():
    src = INVALID["c"][0]
    c, r = call("POST", "/api/compile", {"language": "c", "source": src}); assert c == 200 and not r["ok"]
    c, d = call("POST", "/api/diagnose", {"language": "c", "source": src})
    assert c == 200 and d["root_cause_line"] == 2 and d["reported"]["line"] == 3 and d["patch"]["validation"]["status"] == "fixed"
    c, h = call("GET", "/api/history?limit=5"); assert c == 200 and h["history"][0]["root_line"] == 2


def test_validation_errors():
    assert call("POST", "/api/compile", {"language": "cobol", "source": "x"})[0] == 422
    assert call("POST", "/api/compile", {"language": "c"})[0] == 422
    assert call("POST", "/api/compile", {"language": "c", "source": 5})[0] == 422
    assert call("POST", "/api/diagnose", raw=b"{not json")[0] == 400
    assert call("POST", "/api/compile", {"language": "c", "source": '#include "/etc/passwd"\n'})[0] == 422
    assert call("GET", "/api/nope")[0] == 404


def test_execution_disabled_by_default():
    c, r = call("POST", "/api/run", {"language": "python", "source": "print(1)"}); assert c == 403


def test_execution_when_enabled_runs_and_limits():
    _server(); svc = _S["svc"]; svc.execution_enabled = True
    try:
        c, r = call("POST", "/api/run", {"language": "python", "source": "print('hi')"}); assert c == 200 and r["stdout"].strip() == "hi"
        c, r = call("POST", "/api/run", {"language": "python", "source": "while True: pass", "timeout": 1}); assert r["timed_out"]
        c, r = call("POST", "/api/run", {"language": "c", "source": '#include <stdio.h>\nint main(){printf("c-ok");return 0;}'}); assert r["stdout"] == "c-ok"
    finally:
        svc.execution_enabled = False


def test_patch_requires_explicit_accept_and_revalidates():
    src = INVALID["c"][0]
    c, d = call("POST", "/api/diagnose", {"language": "c", "source": src}); patch = d["patch"]
    c, r = call("POST", "/api/patch/apply", {"language": "c", "source": src, "patch": patch}); assert c == 400
    c, v = call("POST", "/api/patch/validate", {"language": "c", "source": src, "patch": patch}); assert c == 200 and v["validation"]["status"] == "fixed"
    c, r = call("POST", "/api/patch/apply", {"language": "c", "source": src, "patch": patch, "accept": True})
    assert c == 200 and r["revalidation"]["ok"] and r["source"] != src
    bad = dict(patch, edits=[{"offset": 10**6, "delete": 0, "insert": "x"}])
    assert call("POST", "/api/patch/apply", {"language": "c", "source": src, "patch": bad, "accept": True})[0] == 422


def test_counterfactual_endpoint():
    src = INVALID["c"][0]
    c, d = call("POST", "/api/counterfactual", {"language": "c", "source": src})
    assert c == 200
    cf = d["strategies"]["counterfactual"]
    assert cf["root_cause_line"] == 2 and 2 in cf["verified_lines"]
    assert all(cand["line"] <= d["reported"]["line"] for cand in cf["candidates"])
    # same opt-in call also has the ordinary rule/ML output, unchanged
    assert d["strategies"]["rule"]["root_cause_line"] == 2
    # a source with no error is rejected rather than silently returning nothing useful
    c, e = call("POST", "/api/counterfactual", {"language": "python", "source": "print(1)\n"})
    assert c == 409
    # bounds are validated like every other numeric field on this API
    c, e = call("POST", "/api/counterfactual", {"language": "c", "source": src, "max_lines": 0})
    assert c == 422


def test_model_and_benchmark_endpoints_respond():
    c, m = call("GET", "/api/model/status"); assert c == 200 and "available" in m
    c, b = call("GET", "/api/benchmark/results"); assert c == 200 and "available" in b


def test_frontend_api_contract():
    """Static check: every endpoint the React client calls exists on the server (frontend cannot be run offline)."""
    src = open(os.path.join(ROOT, "frontend", "src", "api.ts")).read()
    used = set(re.findall(r"/api/[a-z/]+", src))
    from backend.simple_server import make_handler as mh
    import inspect
    code = inspect.getsource(__import__("backend.simple_server", fromlist=["x"]))
    for u in used:
        assert u in code, f"frontend uses {u} but the server does not define it"
    assert used
