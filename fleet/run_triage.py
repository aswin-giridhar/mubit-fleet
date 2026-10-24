"""Send generated help requests through Mubit for triage, grade them, and log every call.

  python -m fleet.run_triage --count 10 --pilot      # recorded by Mubit, never kept for training
  python -m fleet.run_triage --count 80 --seed 1     # real traffic: becomes training examples
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import triage
from .mubit import TEACHER, BadAnswer, call_json
from .scenarios import generate

RUNS = Path(__file__).resolve().parent.parent / "runs"


def run_one(req, model: str, store: bool) -> dict:
    row = {"incident_id": req.incident_id, "truth": req.truth.__dict__, "model": model, "store": store}
    try:
        pred, meta = call_json(triage.SYSTEM, triage.user_message(req), model=model,
                               session=req.incident_id, store=store)
        row.update(pred=pred, meta=meta, grade=triage.grade(pred, req))
    except BadAnswer as exc:
        row.update(error=f"bad_answer: {exc}")
    except Exception as exc:  # transport/gateway failure: keep it distinct from a wrong answer
        row.update(error=f"call_failed: {type(exc).__name__}: {str(exc)[:200]}")
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model", default=TEACHER)
    ap.add_argument("--pilot", action="store_true", help="send x-middleware-store: false")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    reqs = generate(args.count, seed=args.seed)
    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"triage_{'pilot' if args.pilot else 'live'}_{args.model}_s{args.seed}_{int(time.time())}.jsonl"
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda r: run_one(r, args.model, not args.pilot), reqs))
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    ok = [r for r in rows if "grade" in r]
    errors = Counter(r["error"].split(":")[0] for r in rows if "error" in r)
    print(f"{len(rows)} calls -> {len(ok)} graded, errors: {dict(errors) or 'none'}   log: {out.name}")
    if ok:
        for k in ("category", "valid"):
            print(f"  {k:12s} {sum(r['grade'][k] for r in ok) / len(ok):.0%}")
        lat = sorted(r["meta"]["latency_s"] for r in ok)
        print(f"  latency p50 {lat[len(lat) // 2]:.2f}s  max {lat[-1]:.2f}s   "
              f"tokens in/out avg {sum(r['meta']['input_tokens'] for r in ok) / len(ok):.0f}/"
              f"{sum(r['meta']['output_tokens'] for r in ok) / len(ok):.0f}")
        misses = [r for r in ok if not r["grade"]["category"]]
        for r in misses[:8]:
            print(f"  MISS {r['incident_id']}: truth={r['truth']['category']}  pred={r['pred'].get('category')}")
    for r in [r for r in rows if "error" in r][:3]:
        print("  ERR", r["incident_id"], r["error"][:160])


if __name__ == "__main__":
    main()
