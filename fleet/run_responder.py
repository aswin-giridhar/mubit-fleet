"""Run the responder agent on generated incidents through Mubit, validate its advice, and score it.

  python -m fleet.run_responder --count 10 --pilot
  python -m fleet.run_responder --count 60 --seed 2 --model claude-haiku-4-5
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from .mubit import TEACHER
from .responder import respond
from .scenarios import POLICY, generate
from .world import world_for

RUNS = Path(__file__).resolve().parent.parent / "runs"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model", default=TEACHER)
    ap.add_argument("--pilot", action="store_true", help="send x-middleware-store: false")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    reqs = generate(args.count, seed=args.seed)
    with ThreadPoolExecutor(args.workers) as pool:
        outs = list(pool.map(lambda r: respond(r, model=args.model, store=not args.pilot), reqs))

    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"responder_{'pilot' if args.pilot else 'live'}_{args.model}_s{args.seed}_{int(time.time())}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for req, o in zip(reqs, outs):
            row = asdict(o)
            row.pop("transcript")
            row["truth"] = {"category": req.truth.category, "action": POLICY[req.truth.category][2],
                            "closed_zones": sorted(world_for(req).closed_zones)}
            f.write(json.dumps(row) + "\n")

    n = len(outs)
    errors = [o for o in outs if o.error]
    caught = [o for o in outs if o.violations and o.advice is not None]
    print(f"{n} incidents ({args.model})   log: {out.name}")
    print(f"  correct advice          {sum(o.correct for o in outs) / n:.0%}")
    print(f"  unsafe advice caught    {len(caught)}  -> {Counter(v.split(' ')[0] for o in caught for v in o.violations)}")
    print(f"  escalated to a human    {sum(o.final_action in ('request_human', 'dispatch_event_response') for o in outs) / n:.0%}")
    print(f"  transport errors        {len(errors)}")
    print(f"  avg steps {sum(o.steps for o in outs) / n:.1f}   tokens/incident in {sum(o.input_tokens for o in outs) / n:.0f}"
          f" out {sum(o.output_tokens for o in outs) / n:.0f}   latency p50 {sorted(o.latency_s for o in outs)[n // 2]:.1f}s")
    print(f"  tools used: {dict(Counter(t for o in outs for t in o.tools_called))}")
    for req, o in list(zip(reqs, outs))[:40]:
        if not o.correct:
            print(f"  MISS {o.incident_id} {req.truth.category}: advice={o.advice and o.advice.get('action')}"
                  f" route={o.advice and o.advice.get('route_id')} violations={o.violations} err={o.error}")


if __name__ == "__main__":
    main()
