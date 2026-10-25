"""Demo view: run an incident through Mubit and watch the agent work on a city grid.

  python -m fleet.demo            # then open http://localhost:8765

Each live run streams the agent's steps to the browser (server-sent events) and is saved to
results/demo/, so a recorded run can be replayed later at its original pace, without the network.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import triage
from .mubit import SMALL, TEACHER, BadAnswer, call_json
from .responder import respond
from .scenarios import generate
from .world import world_for

ROOT = Path(__file__).resolve().parent
RECORDINGS = ROOT.parent / "results" / "demo"
# What the Mubit console said about the tasks, copied by hand (there is no read API). Shown with its timestamp.
MUBIT_STATUS = RECORDINGS / "mubit_status.json"
INCIDENTS = generate(30, seed=61)
MODELS = {"sonnet": TEACHER, "haiku": SMALL}


def incident_list() -> list[dict]:
    out = []
    for i, r in enumerate(INCIDENTS):
        w = world_for(r)
        out.append({"index": i, "incident_id": r.incident_id, "vehicle_id": r.vehicle_id, "zone": r.zone,
                    "status": r.planner_status, "closure_nearby": bool(w.closed_zones)})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet during a recording
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj) -> None:
        self._send(200, json.dumps(obj).encode(), "application/json")

    def _stream(self, events) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for e in events:
                self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the viewer closed the tab; the run itself is already recorded

    def do_GET(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self._send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/incidents":
            return self._json(incident_list())
        if url.path == "/api/recordings":
            RECORDINGS.mkdir(parents=True, exist_ok=True)
            return self._json(sorted(p.stem for p in RECORDINGS.glob("*.json")))
        if url.path == "/api/run":
            return self._stream(self._live(int(q.get("i", 0)), MODELS.get(q.get("model", "sonnet"), TEACHER),
                                           q.get("fault") == "1"))
        if url.path == "/api/replay":
            return self._stream(self._replay(q.get("name", ""), float(q.get("speed", 1))))
        self._send(404, b"not found", "text/plain")

    def _live(self, index: int, model: str, fault: bool):
        """Run the incident in a worker thread and yield its events as they arrive."""
        req = INCIDENTS[index % len(INCIDENTS)]
        events: queue.Queue = queue.Queue()
        log: list[dict] = []
        t0 = time.perf_counter()

        def on_event(e: dict) -> None:
            e = {**e, "at": round(time.perf_counter() - t0, 2)}
            log.append(e)
            events.put(e)

        def work() -> None:
            try:
                status = json.loads(MUBIT_STATUS.read_text(encoding="utf-8")) if MUBIT_STATUS.is_file() else {}
                w = world_for(req)
                on_event({"t": "incident", "incident_id": req.incident_id, "vehicle_id": req.vehicle_id,
                          "zone": req.zone, "model": model, "routes": w.route_options, "reports": w.recent_events,
                          "closed_zones": sorted(w.closed_zones), "mubit": status})
                # Task 1 through Mubit: triage. Demo runs are measurements, so Mubit keeps metadata only.
                try:
                    pred, meta = call_json(triage.SYSTEM, triage.user_message(req), model=model,
                                           session=req.incident_id, store=False)
                    on_event({"t": "triage", "category": pred.get("category"), **meta})
                except BadAnswer as exc:
                    on_event({"t": "triage", "category": None, "error": str(exc)})
                # Task 2 through Mubit: the responder. Its own incident event is already shown above.
                respond(req, model=model, store=False, inject_fault=fault,
                        on_event=lambda e: e.get("t") != "incident" and on_event(e))
            except Exception as exc:  # surface the failure in the UI instead of an endless spinner
                on_event({"t": "error", "message": f"{type(exc).__name__}: {exc}"})
            events.put(None)

        threading.Thread(target=work, daemon=True).start()
        while (e := events.get()) is not None:
            yield e
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        name = f"{req.incident_id}_{model}{'_fault' if fault else ''}"
        (RECORDINGS / f"{name}.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        yield {"t": "saved", "name": name}

    def _replay(self, name: str, speed: float):
        path = RECORDINGS / f"{Path(name).name}.json"
        if not path.is_file():
            yield {"t": "error", "message": f"No recording named {name}."}
            return
        last = 0.0
        for e in json.loads(path.read_text(encoding="utf-8")):
            time.sleep(max(0.0, (e.get("at", last) - last) / max(speed, 0.1)))
            last = e.get("at", last)
            yield {**e, "replay": True}


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Demo view on http://localhost:8765  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
