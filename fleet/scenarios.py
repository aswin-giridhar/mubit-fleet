"""Help-request generator with known ground truth.

A vehicle that gets stuck sends a help request: what its planner and perception see, plus free text
from riders, police, staff or the ops log. The generator injects a hidden *cause*, so for every
request we know the right triage and the right advice. The model only ever sees the messy surface.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict

ZONES = [f"Z{r}{c}" for r in "ABCD" for c in range(1, 7)]  # 4 x 6 city grid, e.g. "B3"

CATEGORIES = [
    "double_parked_short",      # driver is right there, unloading: just wait
    "double_parked_abandoned",  # nobody coming back: go around
    "construction_closure",     # road genuinely closed: close the zone for the fleet
    "police_hand_signals",      # an officer is directing traffic: a human must confirm
    "emergency_vehicle",        # siren approaching: hold position
    "debris_small",             # bag, cardboard: proceed slowly
    "debris_large",             # tyre, mattress, ladder: go around
    "sensor_degraded",          # the car can't trust its own eyes: send the event team
    "rider_safety",             # a person in the car needs help: send the event team
    "conflicting_reports",      # what people say contradicts what sensors see: a human decides
]

ACTIONS = ["wait", "reroute", "mark_zone_closed", "proceed_with_caution",
           "request_human", "dispatch_event_response"]

# The fleet's operating policy: hidden cause -> correct triage and advice.
POLICY = {
    "double_parked_short":     ("low",    False, "wait"),
    "double_parked_abandoned": ("medium", False, "reroute"),
    "construction_closure":    ("medium", False, "mark_zone_closed"),
    "police_hand_signals":     ("high",   True,  "request_human"),
    "emergency_vehicle":       ("high",   False, "wait"),
    "debris_small":            ("low",    False, "proceed_with_caution"),
    "debris_large":            ("medium", False, "reroute"),
    "sensor_degraded":         ("high",   True,  "dispatch_event_response"),
    "rider_safety":            ("high",   True,  "dispatch_event_response"),
    "conflicting_reports":     ("high",   True,  "request_human"),
}


@dataclass
class Truth:
    category: str
    urgency: str
    needs_human: bool
    action: str


@dataclass
class HelpRequest:
    incident_id: str
    vehicle_id: str
    zone: str
    blocked_seconds: int
    planner_status: str
    perception: list[dict]
    camera_caption: str
    messages: list[dict]
    truth: Truth = field(repr=False)

    def public(self) -> dict:
        """What the vehicle actually sends: everything except the answer."""
        d = asdict(self)
        d.pop("truth")
        return d


def _typo(rng: random.Random, text: str, rate: float = 0.04) -> str:
    """Drop or double the odd letter, the way people type on a phone in a hurry."""
    out = []
    for ch in text:
        r = rng.random()
        if ch.isalpha() and r < rate / 2:
            continue
        out.append(ch)
        if ch.isalpha() and r > 1 - rate / 2:
            out.append(ch)
    return "".join(out)


def _say(rng: random.Random, source: str, options: list[str]) -> dict:
    return {"from": source, "text": _typo(rng, rng.choice(options))}


NOISE = [
    ("rider", ["can u turn the AC up pls", "how long is this gonna take", "im late for work",
               "is this normal??", "whats going on"]),
    ("ops_log", ["planner: no feasible path in current lane", "localization nominal",
                 "remote request auto-raised after timeout", "battery 64%"]),
]


def _cause(rng: random.Random, category: str) -> tuple[list[dict], str, list[dict], str, int]:
    """Build perception, caption, messages, planner status and blocked time for one cause."""
    lane_obj = lambda t, **kw: {"type": t, "lane": "ego", "distance_m": rng.randint(4, 25), **kw}
    msgs: list[dict] = []

    if category == "double_parked_short":
        p = [lane_obj("van", moving=False, hazard_lights=True),
             {"type": "pedestrian", "lane": "sidewalk", "distance_m": rng.randint(3, 10), "moving": True}]
        cap = rng.choice(["delivery van stopped in lane, person carrying boxes to a shop door",
                          "van stopped in lane with hazard lights on", "stationary van ahead, rear doors open"])
        if rng.random() < 0.6:
            msgs.append(_say(rng, "rider", ["guy is just dropping off a package", "its a delivery van, he's almost done",
                                            "UPS dude unloading, should be quick"]))
        return p, cap, msgs, "stopped: lead vehicle stationary", rng.randint(15, 70)

    if category == "double_parked_abandoned":
        p = [lane_obj("car", moving=False, hazard_lights=rng.random() < 0.5)]
        cap = rng.choice(["parked sedan in travel lane, nobody inside or nearby",
                          "car stopped in lane with hazard lights on", "stationary car ahead, doors closed"])
        if rng.random() < 0.6:
            msgs.append(_say(rng, "rider", ["that car has been there forever, nobody in it",
                                            "no one is coming back to that car lol", "car is empty, just go around it"]))
        return p, cap, msgs, "stopped: lead vehicle stationary", rng.randint(240, 900)

    if category == "construction_closure":
        p = [lane_obj("traffic_cone", moving=False), lane_obj("barrier", moving=False),
             lane_obj("sign", moving=False, text=rng.choice(["ROAD CLOSED", "ROAD CLOSED AHEAD", "DETOUR"]))]
        cap = rng.choice(["row of cones and a ROAD CLOSED barrier across all lanes",
                          "construction crew, barriers across the full road width"])
        msgs.append(_say(rng, "staff", ["crew says the street is shut till tonight",
                                        "roadworks, whole block closed", "they're digging up the whole road"]))
        return p, cap, msgs, "stopped: no drivable path", rng.randint(30, 200)

    if category == "police_hand_signals":
        p = [{"type": "pedestrian", "lane": "intersection", "distance_m": rng.randint(5, 20), "moving": True,
              "attributes": ["high_visibility_vest", "arm_raised"]}]
        cap = rng.choice(["officer in hi-vis in the intersection waving traffic through against the red light",
                          "person in the intersection waving their arms", "traffic lights dark, someone in a vest at the junction"])
        msgs.append(_say(rng, "rider", ["cop is waving us on", "theres a policeman telling cars to go",
                                        "officer keeps pointing at us"]))
        return p, cap, msgs, "yielding: unclassified actor in intersection", rng.randint(10, 60)

    if category == "emergency_vehicle":
        p = [{"type": "fire_truck" if rng.random() < 0.5 else "ambulance", "lane": "oncoming",
              "distance_m": rng.randint(30, 120), "moving": True, "siren": True}]
        cap = rng.choice(["ambulance with lights approaching from behind", "fire engine with sirens coming up the road"])
        msgs.append(_say(rng, "rider", ["theres a siren", "ambulance coming", "fire truck behind us!!"]))
        return p, cap, msgs, "yielding: emergency vehicle detected", rng.randint(5, 40)

    if category == "debris_small":
        item = rng.choice(["plastic_bag", "cardboard_box", "paper_cup"])
        p = [lane_obj("debris", moving=rng.random() < 0.4, size_cm=rng.randint(10, 40), class_guess=item)]
        cap = rng.choice([f"a {item.replace('_', ' ')} on the road, flat and light",
                          "object on the road ahead", "something lying in the lane"])
        msgs.append(_say(rng, "rider", ["its literally a bag", "just a box, drive over it", "theres some trash on the road"]))
        return p, cap, msgs, "stopped: unknown object in path", rng.randint(10, 60)

    if category == "debris_large":
        item = rng.choice(["tyre", "mattress", "ladder", "wooden_pallet"])
        p = [lane_obj("debris", moving=False, size_cm=rng.randint(80, 200), class_guess=item)]
        cap = rng.choice([f"a {item.replace('_', ' ')} lying across the lane",
                          "object on the road ahead", "something lying in the lane"])
        msgs.append(_say(rng, "rider", [f"theres a {item} in the road", "big thing in the road", "something fell off a truck"]))
        return p, cap, msgs, "stopped: obstacle in path", rng.randint(20, 120)

    if category == "sensor_degraded":
        fault = rng.choice(["front camera occluded", "lidar returns degraded", "camera image frozen"])
        p = [{"type": "unknown", "lane": "ego", "distance_m": rng.randint(2, 10), "confidence": round(rng.uniform(0.1, 0.35), 2)}]
        cap = rng.choice(["image mostly dark and smeared, mud or bird droppings on lens", "camera frame unchanged for 40 s"])
        msgs.append({"from": "ops_log", "text": f"health: {fault}, perception confidence low"})
        return p, cap, msgs, "stopped: perception health degraded", rng.randint(10, 90)

    if category == "rider_safety":
        p = [lane_obj("car", moving=True)]
        cap = "normal traffic ahead"
        msgs.append(_say(rng, "rider", ["i feel really sick, chest pain, please help", "someone is banging on the window and shouting",
                                        "i think im going to faint", "theres a guy following the car, im scared"]))
        return p, cap, msgs, "stopped: rider requested assistance", rng.randint(5, 30)

    if category == "conflicting_reports":
        claim, seen = rng.choice([
            ("FIRE!!! smoke everywhere get us out", "food truck with a smoker grill, light smoke, people queuing"),
            ("there was a crash, someone is hurt", "two parked cars, no people on the road, traffic moving normally"),
            ("the road is flooded!!", "dry road surface, wet patch from a street cleaner"),
        ])
        p = [lane_obj("car", moving=False)]
        msgs.append(_say(rng, "rider", [claim]))
        return p, seen, msgs, "stopped: conflicting hazard signals", rng.randint(10, 60)

    raise ValueError(category)


def make_request(rng: random.Random, n: int, category: str | None = None) -> HelpRequest:
    category = category or rng.choice(CATEGORIES)
    perception, caption, msgs, status, blocked = _cause(rng, category)
    for _ in range(rng.choice([0, 1, 1, 2])):  # red herrings that don't change the answer
        src, opts = rng.choice(NOISE)
        msgs.append(_say(rng, src, opts))
    rng.shuffle(msgs)
    urgency, needs_human, action = POLICY[category]
    return HelpRequest(
        incident_id=f"INC-{n:05d}",
        vehicle_id=f"AV-{rng.randint(100, 999)}",
        zone=rng.choice(ZONES),
        blocked_seconds=blocked,
        planner_status=status,
        perception=perception,
        camera_caption=caption,
        messages=msgs,
        truth=Truth(category, urgency, needs_human, action),
    )


def generate(count: int, seed: int = 0, categories: list[str] | None = None) -> list[HelpRequest]:
    """Balanced across the given categories (all of them by default)."""
    rng = random.Random(seed)
    pool = categories or CATEGORIES
    cats = [pool[i % len(pool)] for i in range(count)]
    rng.shuffle(cats)
    return [make_request(rng, seed * 100000 + i, c) for i, c in enumerate(cats)]
