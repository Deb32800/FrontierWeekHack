import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"
GDACS_SEARCH = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

# Heuristic model, stated openly on the slides: radius of damaging impact by quake magnitude,
# GDACS alert level for other hazards, and downtime by distance zone.
EQ_RADIUS = [(5.5, 20), (6.0, 50), (6.5, 80), (7.0, 120), (7.5, 200), (8.0, 300), (99, 500)]
GDACS_RADIUS = {"Red": 300, "Orange": 150, "Green": 50}
DOWNTIME = {"EQ": {"severe": 28, "moderate": 14, "minor": 5}, "OTHER": {"severe": 21, "moderate": 10, "minor": 4}}
ALT_PREMIUM = {"A": 0.08, "B": 0.12}
ALT_SETUP_DAYS = 14
AIR_FREIGHT_DAYS = 1
AIR_PREMIUM = 0.20
AIR_BATCH_DAYS = 30


def _load(name):
    return json.loads((DATA / name).read_text())


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def impact_radius_km(event):
    if event["type"] == "EQ":
        return next(r for m, r in EQ_RADIUS if event["magnitude"] < m)
    return GDACS_RADIUS.get(event.get("alert_level"), 50)


def _usgs_to_event(f):
    p, c = f["properties"], f["geometry"]["coordinates"]
    ev = {
        "event_id": f["id"], "source": "USGS", "type": "EQ", "title": p["title"],
        "magnitude": p["mag"], "alert_level": (p.get("alert") or "none").capitalize(),
        "lat": c[1], "lon": c[0], "depth_km": c[2],
        "time": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat(),
        "url": p.get("url"),
    }
    ev["impact_radius_km"] = impact_radius_km(ev)
    return ev


def _gdacs_to_event(f):
    p, g = f["properties"], f["geometry"]["coordinates"]
    ev = {
        "event_id": f"GDACS-{p.get('eventtype')}-{p.get('eventid')}", "source": "GDACS",
        "type": p.get("eventtype"), "title": p.get("name"), "magnitude": None,
        "alert_level": p.get("alertlevel"), "lat": g[1], "lon": g[0],
        "time": p.get("fromdate"), "country": p.get("country"),
        "url": (p.get("url") or {}).get("report"),
    }
    ev["impact_radius_km"] = impact_radius_km(ev)
    return ev


def fetch_live_events(min_magnitude=5.5, gdacs_days=30):
    events = []
    r = requests.get(USGS_FEED, timeout=20)
    r.raise_for_status()
    events += [_usgs_to_event(f) for f in r.json()["features"] if (f["properties"]["mag"] or 0) >= min_magnitude]
    today = datetime.now(timezone.utc).date()
    try:
        g = requests.get(GDACS_SEARCH, timeout=20, params={
            "eventlist": "TC;FL;VO;WF", "alertlevel": "Orange;Red",
            "fromdate": str(today - timedelta(days=gdacs_days)), "todate": str(today),
        })
        g.raise_for_status()
        events += [_gdacs_to_event(f) for f in g.json().get("features", []) if isinstance(f["geometry"]["coordinates"][0], (int, float))]
    except (requests.RequestException, ValueError):
        pass
    return events


def fetch_usgs_event(event_id):
    r = requests.get(USGS_QUERY, timeout=20, params={"format": "geojson", "eventid": event_id})
    r.raise_for_status()
    return _usgs_to_event(r.json())


def downtime_multiplier(event):
    m = event.get("magnitude") or 0
    return 3 if m >= 8.5 else 2 if m >= 8.0 else 1


def exposed_suppliers(event):
    radius = event["impact_radius_km"]
    kind = "EQ" if event["type"] == "EQ" else "OTHER"
    mult = downtime_multiplier(event)
    hits = []
    for s in _load("suppliers.json"):
        d = haversine_km(event["lat"], event["lon"], s["lat"], s["lon"])
        if d > radius:
            continue
        zone = "severe" if d <= radius / 3 else "moderate" if d <= 2 * radius / 3 else "minor"
        hits.append({**s, "distance_km": round(d), "zone": zone, "est_downtime_days": DOWNTIME[kind][zone] * mult})
    return sorted(hits, key=lambda h: h["distance_km"])


def _alternatives(part, exposed_ids, stockout_day, recovery_day):
    suppliers = {s["supplier_id"]: s for s in _load("suppliers.json")}
    options = []
    for sid in part["qualified_alternates"]:
        if sid in exposed_ids:
            continue
        s = suppliers[sid]
        available_day = ALT_SETUP_DAYS + s["transit_days_to_osaka"]
        premium = ALT_PREMIUM[s["reliability_tier"]]
        cover_days = max(0, recovery_day - max(stockout_day, 0))
        units = math.ceil(part["daily_usage_units"] * (recovery_day - available_day + 14)) if recovery_day > available_day else 0
        options.append({
            "supplier_id": sid, "name": s["name"], "city": s["city"], "country": s["country"],
            "available_on_day": available_day, "cost_premium_pct": round(premium * 100),
            "closes_gap": available_day <= stockout_day,
            "residual_gap_days": max(0, min(recovery_day, available_day) - stockout_day),
            "po_units": units, "po_value_usd": round(units * part["unit_cost_usd"] * (1 + premium)),
            "gap_days_addressed": cover_days,
        })
    return sorted(options, key=lambda o: (o["residual_gap_days"], o["cost_premium_pct"]))


def _expedite(part, downtime, stockout_day):
    new_recovery = downtime + AIR_FREIGHT_DAYS
    units = math.ceil(part["daily_usage_units"] * AIR_BATCH_DAYS)
    return {
        "new_recovery_day": new_recovery,
        "residual_gap_days": round(max(0.0, new_recovery - stockout_day), 1),
        "cost_usd": round(units * part["unit_cost_usd"] * AIR_PREMIUM),
    }


def _plan(row):
    options = [("wait", row["est_recovery_day"], 0, None)]
    ex = row["expedite"]
    options.append(("expedite_air_freight", ex["new_recovery_day"], ex["cost_usd"], None))
    for alt in row.get("alternatives", []):
        if alt["po_units"]:
            options.append(("switch_to_alternate", alt["available_on_day"], alt["po_value_usd"], alt))
    best = min(options, key=lambda o: (max(0.0, o[1] - row["days_of_cover"]), o[2]))
    return {
        "action": best[0], "effective_recovery_day": best[1], "cost_usd": best[2],
        "residual_gap_days": round(max(0.0, best[1] - row["days_of_cover"]), 1),
        "alternate": best[3]["supplier_id"] if best[3] else None,
    }


def _orders_hit(gapped, recovery_key, products, orders, horizon_days):
    windows = {}
    for prod in products:
        blockers = [gapped[pid] for pid in prod["bom"] if pid in gapped and gapped[pid][recovery_key] > gapped[pid]["days_of_cover"]]
        if blockers:
            windows[prod["product_id"]] = {
                "product_id": prod["product_id"], "name": prod["name"],
                "blocked_from_day": min(b["days_of_cover"] for b in blockers),
                "blocked_until_day": max(b[recovery_key] for b in blockers),
                "blocking_parts": [b["part_id"] for b in blockers],
            }
    hit = [
        o for o in orders
        if (w := windows.get(o["product_id"])) and w["blocked_from_day"] <= o["due_in_days"] <= w["blocked_until_day"]
        and o["due_in_days"] <= horizon_days
    ]
    return list(windows.values()), hit


def assess(event, horizon_days=90):
    company = _load("company.json")
    parts = _load("parts.json")
    products = _load("products.json")
    orders = _load("orders.json")
    hits = exposed_suppliers(event)
    hit_by_id = {h["supplier_id"]: h for h in hits}

    part_rows = []
    for p in parts:
        h = hit_by_id.get(p["primary_supplier"])
        if not h:
            continue
        recovery_day = h["est_downtime_days"] + h["transit_days_to_osaka"]
        stockout_day = p["days_of_cover"]
        gap = max(0.0, recovery_day - stockout_day)
        row = {
            "part_id": p["part_id"], "name": p["name"], "supplier_id": h["supplier_id"],
            "supplier": h["name"], "supplier_city": h["city"], "distance_km": h["distance_km"], "zone": h["zone"],
            "days_of_cover": stockout_day, "est_recovery_day": recovery_day, "supply_gap_days": round(gap, 1),
            "at_risk": gap > 0,
        }
        if gap > 0:
            row["alternatives"] = _alternatives(p, set(hit_by_id), stockout_day, recovery_day)
            row["expedite"] = _expedite(p, h["est_downtime_days"], stockout_day)
            row["recommended"] = _plan(row)
            row["mitigated_recovery_day"] = row["recommended"]["effective_recovery_day"]
        part_rows.append(row)

    gapped = {r["part_id"]: r for r in part_rows if r["at_risk"]}
    product_rows, orders_at_risk = _orders_hit(gapped, "est_recovery_day", products, orders, horizon_days)
    _, orders_after = _orders_hit(gapped, "mitigated_recovery_day", products, orders, horizon_days)

    windows = {p["product_id"]: p for p in product_rows}
    terms = {c["customer"]: c for c in _load("contracts.json")["customers"]}
    for o in orders_at_risk:
        t = terms[o["customer"]]
        days_late = max(0.0, windows[o["product_id"]]["blocked_until_day"] - o["due_in_days"])
        weeks = math.ceil(days_late / 7) if days_late else 0
        pct = min(t["late_delivery_penalty_pct_per_week"] * weeks, t["penalty_cap_pct"])
        o["est_days_late"] = round(days_late, 1)
        o["penalty_pct"] = pct
        o["penalty_usd"] = round(o["value_usd"] * pct / 100)
        o["notify_customer_by_day"] = max(0, round(o["due_in_days"] - t["notification_required_days"]))

    revenue = sum(o["value_usd"] for o in orders_at_risk)
    revenue_after = sum(o["value_usd"] for o in orders_after)
    plan_cost = sum(r["recommended"]["cost_usd"] for r in gapped.values())
    po_value = sum(r["recommended"]["cost_usd"] for r in gapped.values() if r["recommended"]["action"] == "switch_to_alternate")
    severity = (
        "none" if not hits else
        "watch" if not gapped else
        "critical" if revenue >= 1_000_000 or any(r["zone"] == "severe" for r in gapped.values()) else
        "high"
    )
    return {
        "event": event,
        "company": company["name"],
        "severity": severity,
        "exposed_suppliers": hits,
        "parts": part_rows,
        "products_blocked": product_rows,
        "orders_at_risk": orders_at_risk,
        "orders_still_at_risk_after_plan": orders_after,
        "summary": {
            "suppliers_exposed": len(hits),
            "parts_exposed": len(part_rows),
            "parts_with_supply_gap": len(gapped),
            "products_blocked": len(product_rows),
            "orders_at_risk": len(orders_at_risk),
            "strategic_orders_at_risk": sum(1 for o in orders_at_risk if o["priority"] == "strategic"),
            "revenue_at_risk_usd": revenue,
            "penalty_exposure_usd": sum(o["penalty_usd"] for o in orders_at_risk),
            "revenue_at_risk_after_plan_usd": revenue_after,
            "revenue_protected_usd": revenue - revenue_after,
            "plan_cost_usd": plan_cost,
            "alternate_po_value_usd": po_value,
            "requires_human_approval": plan_cost > company["approval_limit_usd"],
            "approval_limit_usd": company["approval_limit_usd"],
        },
        "model_assumptions": {
            "eq_impact_radius_km": EQ_RADIUS, "gdacs_radius_km": GDACS_RADIUS,
            "downtime_days_by_zone": DOWNTIME, "downtime_multiplier_applied": downtime_multiplier(event),
            "alt_supplier_setup_days": ALT_SETUP_DAYS,
            "air_freight_days": AIR_FREIGHT_DAYS, "air_premium_pct": round(AIR_PREMIUM * 100),
        },
    }


def simulate(lat, lon, magnitude, label="What-if scenario"):
    ev = {
        "event_id": f"SIM-{lat:.2f}-{lon:.2f}-M{magnitude}", "source": "SIMULATION", "type": "EQ",
        "title": f"[SIMULATION] {label}", "magnitude": magnitude, "alert_level": "Simulated",
        "lat": lat, "lon": lon, "depth_km": 10, "time": datetime.now(timezone.utc).isoformat(), "url": None,
    }
    ev["impact_radius_km"] = impact_radius_km(ev)
    return assess(ev)


def scan_live(min_magnitude=5.5):
    results = []
    for ev in fetch_live_events(min_magnitude):
        a = assess(ev)
        results.append({"event": ev, "severity": a["severity"], **a["summary"]})
    return sorted(results, key=lambda r: -r["revenue_at_risk_usd"])


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        for r in scan_live():
            e = r["event"]
            print(f"{r['severity']:8} {e['source']:5} {e['type']:3} {str(e.get('magnitude') or e['alert_level']):6} "
                  f"{e['title'][:48]:48} suppliers={r['suppliers_exposed']} risk=${r['revenue_at_risk_usd']:,}")
    else:
        ev_id = sys.argv[1] if len(sys.argv) > 1 else "us7000m9g4"
        print(json.dumps(assess(fetch_usgs_event(ev_id))["summary"], indent=2))
