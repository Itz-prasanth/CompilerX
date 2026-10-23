"""SQLite persistence for diagnostic history and benchmark runs."""
import json, os, sqlite3, time, threading

_LOCK = threading.Lock()


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, language TEXT,
                         status TEXT, source_sha TEXT, source TEXT, reported_line INTEGER, root_line INTEGER, strategy TEXT,
                         category TEXT, message TEXT, patch_status TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS benchmark_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, split TEXT, n_samples INTEGER, results TEXT)""")

    def _conn(self):
        c = sqlite3.connect(self.path, timeout=10); c.row_factory = sqlite3.Row; return c

    def add_history(self, language, source, r):
        patch = (r.get("patch") or {}).get("validation") or {}
        with _LOCK, self._conn() as c:
            c.execute("INSERT INTO history(ts,language,status,source_sha,source,reported_line,root_line,strategy,category,message,patch_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), language, r.get("status"), r.get("source_sha256"), source,
                       (r.get("reported") or {}).get("line"), r.get("root_cause_line"), r.get("primary_strategy"), r.get("category"),
                       (r.get("reported") or {}).get("message"), patch.get("status")))

    def history(self, limit=50):
        with self._conn() as c:
            return [dict(x) for x in c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (int(limit),))]

    def clear_history(self):
        with _LOCK, self._conn() as c:
            c.execute("DELETE FROM history")

    def add_benchmark(self, res):
        with _LOCK, self._conn() as c:
            c.execute("INSERT INTO benchmark_runs(ts,split,n_samples,results) VALUES(?,?,?,?)", (res["created"], res["split"], res["n_samples"], json.dumps(res)))

    def latest_benchmark(self):
        with self._conn() as c:
            row = c.execute("SELECT results FROM benchmark_runs ORDER BY id DESC LIMIT 1").fetchone()
            return json.loads(row["results"]) if row else None
