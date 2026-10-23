import json, logging, sys, time


class JsonFormatter(logging.Formatter):
    def format(self, r):
        d = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(r.created)), "level": r.levelname, "logger": r.name, "msg": r.getMessage()}
        d.update(getattr(r, "extra_fields", {}))
        return json.dumps(d)


def setup(level=logging.INFO):
    h = logging.StreamHandler(sys.stderr); h.setFormatter(JsonFormatter())
    root = logging.getLogger("compilerx"); root.handlers[:] = [h]; root.setLevel(level)
    return root
