import json
import re

import engine

_events = {}


def _remember(ev):
    _events[ev["event_id"]] = ev
    return ev


def resolve_event(event_id):
    if event_id in _events:
        return _events[event_id]
    m = re.match(r"SIM-(-?[\d.]+)-(-?[\d.]+)-M([\d.]+)", event_id)
    if m:
        return _remember(engine.simulate(float(m[1]), float(m[2]), float(m[3]))["event"])
    if event_id.startswith("GDACS-"):
        for ev in engine.fetch_live_events():
            _remember(ev)
        if event_id in _events:
            return _events[event_id]
        raise ValueError(f"GDACS event {event_id} not found in the last 30 days")
    return _remember(engine.fetch_usgs_event(event_id))


def scan_live_events(min_magnitude=5.5):
    rows = []
    for ev in engine.fetch_live_events(float(min_magnitude)):
        _remember(ev)
        hits = engine.exposed_suppliers(ev)
        rows.append({
            "event_id": ev["event_id"], "source": ev["source"], "type": ev["type"], "title": ev["title"],
            "magnitude": ev["magnitude"], "alert_level": ev["alert_level"], "time": ev["time"],
            "lat": ev["lat"], "lon": ev["lon"], "impact_radius_km": ev["impact_radius_km"],
            "helix_suppliers_in_radius": [f"{h['supplier_id']} {h['name']} ({h['city']}, {h['distance_km']} km)" for h in hits],
        })
    return {"events_scanned": len(rows), "events": sorted(rows, key=lambda r: -len(r["helix_suppliers_in_radius"]))}


def get_event(event_id):
    return resolve_event(event_id)


def simulate_event(lat, lon, magnitude, label="What-if scenario"):
    ev = engine.simulate(float(lat), float(lon), float(magnitude), label)["event"]
    return _remember(ev)


def get_exposure(event_id):
    a = engine.assess(resolve_event(event_id))
    hidden = ("alternatives", "expedite", "recommended", "mitigated_recovery_day")
    return {
        "event": a["event"], "severity": a["severity"],
        "exposed_suppliers": a["exposed_suppliers"],
        "parts": [{k: v for k, v in p.items() if k not in hidden} for p in a["parts"]],
        "products_blocked": a["products_blocked"],
        "orders_at_risk": a["orders_at_risk"],
        "summary": {k: a["summary"][k] for k in ("suppliers_exposed", "parts_exposed", "parts_with_supply_gap",
                                                 "products_blocked", "orders_at_risk", "strategic_orders_at_risk",
                                                 "revenue_at_risk_usd", "penalty_exposure_usd")},
        "model_assumptions": a["model_assumptions"],
    }


def get_contract_terms(supplier_ids=None, customers=None):
    if isinstance(supplier_ids, str):
        supplier_ids = [s.strip() for s in supplier_ids.split(",") if s.strip()]
    if isinstance(customers, str):
        customers = [c.strip() for c in customers.split(",") if c.strip()]
    c = json.loads((engine.DATA / "contracts.json").read_text())
    return {
        "suppliers": [s for s in c["suppliers"] if not supplier_ids or s["supplier_id"] in supplier_ids],
        "customers": [x for x in c["customers"] if not customers or x["customer"] in customers],
    }


def get_mitigation_options(event_id):
    a = engine.assess(resolve_event(event_id))
    keep = ("part_id", "name", "supplier", "supplier_city", "zone", "days_of_cover",
            "est_recovery_day", "supply_gap_days", "alternatives", "expedite", "recommended")
    return {
        "event_id": a["event"]["event_id"],
        "parts_with_gap": [{k: p[k] for k in keep} for p in a["parts"] if p["at_risk"]],
        "orders_still_at_risk_after_plan": a["orders_still_at_risk_after_plan"],
        "summary": a["summary"],
    }
