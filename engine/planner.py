"""30-day content plan per account.

Every posting slot for the next 30 days gets a product, an angle, a weekly goal, a format (video or Instagram
carousel) and, on test days, an A/B pair: same product and angle, two different hooks, back to back.
The plan is rebuilt forward from today each day using what has actually performed (engine/insights.py), so
subjects and angles that earn more views and engagement get more of the remaining slots. Past days never change.

Saved to content/plans/<account>.json. run.py follows it whenever it writes a script itself; scripts already
waiting in content/queue/ still go first.
"""
import datetime as dt
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLANS = os.path.join(ROOT, "content", "plans")
DAYS = 30
# UTC hour -> platforms. 4 TikTok + 2 Instagram per account per day (8am, 11am, 2pm, 6pm ET during EDT).
# GitHub often starts scheduled runs late, so a run belongs to the nearest slot at or before its start hour.
SCHEDULE = {12: ["tiktok"], 15: ["tiktok", "instagram"], 18: ["tiktok"], 22: ["tiktok", "instagram"]}
PHASES = [
    (7, "introduce", "Introduce the brand: who it is and what it offers."),
    (14, "story", "Tell the story: why this exists and who it is for."),
    (22, "show", "Show the product in use: what it does and what makes it different."),
    (DAYS, "ask", "Ask for the action: point clearly to the call to action."),
]
AB_EVERY = 2          # an A/B hook test every 2nd day, on that day's first two TikTok slots
CAROUSEL_EVERY = 3    # every 3rd Instagram slot is a carousel instead of a Reel
MIN_W, MAX_W = 0.5, 2.0


def slot_hour(hour):
    """The schedule slot a run started at `hour` UTC belongs to."""
    for h in sorted(SCHEDULE, reverse=True):
        if hour >= h:
            return h
    return max(SCHEDULE)  # just after midnight UTC = the previous evening's late slot


def phase(day_index):
    for last, name, focus in PHASES:
        if day_index < last:
            return name, focus
    return PHASES[-1][1], PHASES[-1][2]


class Rotation:
    """Smooth weighted round-robin: everything gets a turn, heavier items come round more often."""

    def __init__(self, items, weights=None):
        self.items = list(items)
        w = weights or {}
        self.weights = [min(max(float(w.get(i, 1.0)), MIN_W), MAX_W) for i in self.items]
        self.current = [0.0] * len(self.items)

    def next(self):
        total = sum(self.weights)
        for i, w in enumerate(self.weights):
            self.current[i] += w
        best = max(range(len(self.items)), key=lambda i: self.current[i])
        self.current[best] -= total
        return self.items[best]


def build(acct, start, days=DAYS, weights=None, first_day_index=0, ig_count=0, skip=0):
    """Slots for `days` days from `start` (a date). weights: {"products": {id: w}, "angles": {"id|angle": w}}.
    skip: picks already used by earlier days of the same plan, so a rebuild carries the rotation on."""
    weights = weights or {}
    products = acct["products"]
    prod_rot = Rotation([p["id"] for p in products], weights.get("products"))
    by_id = {p["id"]: p for p in products}
    angle_rot = {}
    for p in products:
        angles = p.get("angles") or [p["pitch"]]
        aw = {a: (weights.get("angles") or {}).get(f"{p['id']}|{a}", 1.0) for a in angles}
        angle_rot[p["id"]] = Rotation(angles, aw)

    for _ in range(skip):
        angle_rot[prod_rot.next()].next()

    slots = []
    for d in range(days):
        date = start + dt.timedelta(days=d)
        day_index = first_day_index + d
        name, focus = phase(day_index)
        test_day = day_index % AB_EVERY == 0
        tiktok_n, pair = 0, None
        for hour in sorted(SCHEDULE):
            for platform in SCHEDULE[hour]:
                if platform not in acct.get("platforms", ["tiktok", "instagram"]):
                    continue
                slot = {"date": date.isoformat(), "hour_utc": hour, "platform": platform, "phase": name,
                        "focus": focus, "format": "video", "experiment": None, "variant": None}
                if platform == "tiktok":
                    tiktok_n += 1
                    if test_day and tiktok_n == 2 and pair:
                        slot.update(product=pair["product"], angle=pair["angle"], experiment=pair["experiment"], variant="B")
                        slots.append(slot)
                        continue
                else:
                    ig_count += 1
                    if ig_count % CAROUSEL_EVERY == 0:
                        slot["format"] = "carousel"
                pid = prod_rot.next()
                slot.update(product=pid, angle=angle_rot[pid].next())
                if platform == "tiktok" and test_day and tiktok_n == 1:
                    slot.update(experiment=f"{acct['id']}-{date.strftime('%Y%m%d')}", variant="A")
                    pair = slot
                slots.append(slot)
    assert all(s["product"] in by_id for s in slots)
    return slots


def path(account_id):
    return os.path.join(PLANS, f"{account_id}.json")


def load(account_id):
    try:
        with open(path(account_id)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def refresh(acct, today=None, weights=None):
    """Create the plan, or keep its past days and rebuild today onward with current weights.
    A plan that has run its 30 days is replaced by a new one starting today."""
    today = today or dt.datetime.utcnow().date()
    old = load(acct["id"])
    valid = {p["id"] for p in acct["products"]}
    start, kept = today, []
    if old:
        old_start = dt.date.fromisoformat(old["start"])
        if (today - old_start).days < old["days"]:
            start = old_start
            kept = [s for s in old["slots"] if s["date"] < today.isoformat() and s["product"] in valid]
    done = (today - start).days
    ig_done = sum(1 for s in kept if s["platform"] == "instagram")
    picks = sum(1 for s in kept if s["variant"] != "B")
    slots = kept + build(acct, today, DAYS - done, weights, first_day_index=done, ig_count=ig_done, skip=picks)
    plan = {"account": acct["id"], "brand": acct["brand"], "start": start.isoformat(), "days": DAYS,
            "end": (start + dt.timedelta(days=DAYS - 1)).isoformat(),
            "updated_at": dt.datetime.utcnow().isoformat() + "Z",
            "weights": weights or {}, "phases": [{"through_day": last, "name": n, "focus": f} for last, n, f in PHASES],
            "slots": slots}
    os.makedirs(PLANS, exist_ok=True)
    with open(path(acct["id"]), "w") as f:
        json.dump(plan, f, indent=1)
    return plan


def slot_for(account_id, now, platform):
    """The planned slot for this account, platform and moment (a UTC datetime), or None."""
    plan = load(account_id)
    if not plan:
        return None
    hour = slot_hour(now.hour)
    date = now.date() if now.hour >= min(SCHEDULE) else now.date() - dt.timedelta(days=1)
    for s in plan["slots"]:
        if s["date"] == date.isoformat() and s["hour_utc"] == hour and s["platform"] == platform:
            return s
    return None
