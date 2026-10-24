"""Scoreboard: the same incidents, answered by each model, judged against the known correct advice.

  python -m fleet.scoreboard --count 40 --seed 61 --models claude-sonnet-4-5,claude-haiku-4-5

Runs are pilots (Mubit records them without their content), so a comparison never becomes training data.
Writes results/scoreboard.md and results/scoreboard.json.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .responder import respond
from .scenarios import CATEGORIES, POLICY, generate

RESULTS = Path(__file__).resolve().parent.parent / "results"

# USD per million tokens (input, output), list prices. Haiku 4.5 is from the Claude API reference;
# Sonnet 4.5 is assumed to share Sonnet 4.6's $3/$15. Estimates, not an invoice.
PRICE = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-4-5": (3.0, 15.0)}


def summarise(model: str, reqs, outs) -> dict:
    n = len(outs)
    lat = sorted(o.latency_s for o in outs)
    tin = sum(o.input_tokens for o in outs) / n
    tout = sum(o.output_tokens for o in outs) / n
    pin, pout = PRICE.get(model, (float("nan"), float("nan")))
    by_cat = defaultdict(lambda: [0, 0])
    for r, o in zip(reqs, outs):
        by_cat[r.truth.category][0] += o.correct
        by_cat[r.truth.category][1] += 1
    return {
        "model": model,
        "incidents": n,
        "correct_advice": sum(o.correct for o in outs) / n,
        "unsafe_advice_blocked": sum(bool(o.violations) and o.advice is not None for o in outs),
        "escalated_to_human": sum(o.final_action in ("request_human", "dispatch_event_response") for o in outs) / n,
        "no_advice": sum(o.advice is None for o in outs),
        "transport_errors": sum(bool(o.error) for o in outs),
        "latency_p50_s": lat[n // 2],
        "latency_p90_s": lat[int(n * 0.9) - 1],
        "steps_avg": sum(o.steps for o in outs) / n,
        "tokens_in_avg": tin,
        "tokens_out_avg": tout,
        "usd_per_1000_incidents": (tin * pin + tout * pout) / 1000,
        "by_category": {c: f"{k}/{t}" for c, (k, t) in sorted(by_cat.items())},
        "misses": [{"incident": o.incident_id, "category": r.truth.category,
                    "expected": POLICY[r.truth.category][2],
                    "advised": o.advice and o.advice.get("action"),
                    "violations": o.violations, "request_ids": o.request_ids}
                   for r, o in zip(reqs, outs) if not o.correct],
    }


def to_markdown(rows: list[dict], seed: int) -> str:
    cols = [("Correct advice", lambda r: f"{r['correct_advice']:.0%}"),
            ("Unsafe advice blocked by code", lambda r: str(r["unsafe_advice_blocked"])),
            ("Escalated to a human", lambda r: f"{r['escalated_to_human']:.0%}"),
            ("Latency p50 / p90", lambda r: f"{r['latency_p50_s']:.1f}s / {r['latency_p90_s']:.1f}s"),
            ("Calls per incident", lambda r: f"{r['steps_avg']:.1f}"),
            ("Tokens per incident (in / out)", lambda r: f"{r['tokens_in_avg']:.0f} / {r['tokens_out_avg']:.0f}"),
            ("Est. $ per 1,000 incidents", lambda r: f"${r['usd_per_1000_incidents']:.2f}")]
    head = "| | " + " | ".join(r["model"] for r in rows) + " |"
    sep = "|---|" + "---|" * len(rows)
    body = "\n".join(f"| {name} | " + " | ".join(f(r) for r in rows) + " |" for name, f in cols)
    cats = "\n".join(f"| {c} | " + " | ".join(r["by_category"].get(c, "–") for r in rows) + " |" for c in CATEGORIES)
    return (f"# Scoreboard\n\n{rows[0]['incidents']} generated incidents (seed {seed}), identical for every model. "
            "Correct = the advice matches the fleet policy for the injected cause and passes the safety validator.\n\n"
            f"{head}\n{sep}\n{body}\n\n## Correct advice by incident type\n\n{head}\n{sep}\n{cats}\n\n"
            "Costs are estimates from list prices; latency is measured end to end through Mubit.\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=61)
    ap.add_argument("--models", default="claude-sonnet-4-5,claude-haiku-4-5")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    reqs = generate(args.count, seed=args.seed)
    rows = []
    for model in args.models.split(","):
        with ThreadPoolExecutor(args.workers) as pool:
            outs = list(pool.map(lambda r: respond(r, model=model, store=False), reqs))
        rows.append(summarise(model, reqs, outs))
        print(f"{model}: correct {rows[-1]['correct_advice']:.0%}, p50 {rows[-1]['latency_p50_s']:.1f}s, "
              f"${rows[-1]['usd_per_1000_incidents']:.2f}/1k incidents")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "scoreboard.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (RESULTS / "scoreboard.md").write_text(to_markdown(rows, args.seed), encoding="utf-8")
    print(f"wrote {RESULTS / 'scoreboard.md'}")


if __name__ == "__main__":
    main()
