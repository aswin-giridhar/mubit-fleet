"""Task 1: triage a help request.

The system prompt is frozen. Mubit groups calls into a task by model + instructions + tools + output
format, so any edit here starts a new task and resets its example count. Everything that varies
lives in the user message.
"""
from __future__ import annotations

import json

from .scenarios import CATEGORIES, HelpRequest

SYSTEM = """You are the first-line triage agent for a fleet of autonomous vehicles.
A vehicle has stopped and asked for help. You receive what its planner and perception report, a camera caption,
and free-text messages from riders, staff, police or the ops log. Messages can be noisy, misspelled or irrelevant.

Classify the request into exactly one category:
- double_parked_short: a vehicle is stopped in the lane but its driver is present and about to leave (e.g. unloading).
- double_parked_abandoned: a vehicle is stopped in the lane with nobody present and no sign of leaving.
- construction_closure: the road ahead is closed by works, barriers or closure signs.
- police_hand_signals: a police officer or traffic marshal is directing traffic by hand.
- emergency_vehicle: an emergency vehicle with lights or siren is approaching or nearby.
- debris_small: a small, light object (bag, cardboard, cup) is in the lane.
- debris_large: a large or heavy object (tyre, mattress, ladder, pallet) is in the lane.
- sensor_degraded: the vehicle's own sensors are unreliable (occluded, frozen, degraded).
- rider_safety: a person in or around the vehicle needs urgent help or feels threatened.
- conflicting_reports: what people report clearly contradicts what the sensors and camera show.

Weigh all the evidence: how long the vehicle has been blocked, object sizes, who is present, and whether the
messages agree with the sensors. Captions can be vague, and a single message can be wrong.

Reply with JSON only, no prose:
{"category": "<category>"}"""


def user_message(req: HelpRequest) -> str:
    return json.dumps(req.public(), indent=1)


def grade(pred: dict, req: HelpRequest) -> dict:
    # Urgency, escalation and the advice itself come from the fleet policy in code, not the model.
    return {
        "category": pred.get("category") == req.truth.category,
        "valid": pred.get("category") in CATEGORIES,
    }
