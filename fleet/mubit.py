"""One Anthropic client, pointed at Mubit. Every model call in the project goes through here."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TEACHER = "claude-sonnet-4-5"   # the frontier model whose answers Mubit distils
SMALL = "claude-haiku-4-5"      # stand-in for the small tier until adapters can be called by API

client = Anthropic(
    base_url=os.environ.get("MUBIT_BASE_URL", "https://api.mubit.ai/anthropic"),
    api_key=os.environ["MUBIT_API_KEY"],
)


class BadAnswer(Exception):
    """The call succeeded but the reply is not the JSON we asked for."""


def record_headers(store: bool = True, sensitive: bool = False) -> dict:
    """Mubit's data controls. A header can only lower what Mubit keeps of a call.

    store=False: pilot/measurement runs, counted but never kept as training examples.
    sensitive:   the call carries a person's own words about their health or safety, so Mubit keeps
                 metadata only and never stores the text or trains on it.
    """
    if not store or sensitive:
        return {"x-middleware-record": "metadata"}
    return {}


def create(**kwargs):
    """messages.create through Mubit, returning the parsed reply plus Mubit's request id."""
    raw = client.messages.with_raw_response.create(**kwargs)
    return raw.parse(), raw.headers.get("x-middleware-request-id")


def call_json(system: str, user: str, *, model: str, session: str, store: bool = True,
              max_tokens: int = 300) -> tuple[dict, dict]:
    """Send one call through Mubit and parse the JSON reply.

    `session` becomes metadata.user_id, the session field Mubit reads on the Anthropic route; Mubit
    sets test cases aside by session, so one incident never leaks between training and testing.
    """
    t0 = time.perf_counter()
    resp, request_id = create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        metadata={"user_id": session},
        extra_headers=record_headers(store),
    )
    latency = time.perf_counter() - t0
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise BadAnswer(f"no JSON object in reply: {text[:120]!r}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise BadAnswer(f"unparseable JSON: {text[:120]!r}") from exc
    meta = {"latency_s": round(latency, 3), "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens, "served_model": resp.model,
            "request_id": request_id}
    return data, meta
