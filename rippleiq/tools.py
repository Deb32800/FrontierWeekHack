import json

from azure.ai.projects.models import FunctionTool

from service import (get_contract_terms, get_event, get_exposure, get_mitigation_options,  # noqa: F401
                     resolve_event, scan_live_events, simulate_event)


REGISTRY = {
    "scan_live_events": scan_live_events,
    "get_event": get_event,
    "simulate_event": simulate_event,
    "get_exposure": get_exposure,
    "get_contract_terms": get_contract_terms,
    "get_mitigation_options": get_mitigation_options,
}


def call(name, arguments):
    fn = REGISTRY.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(**json.loads(arguments or "{}")), default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


def _tool(name, description, properties=None, required=None):
    return FunctionTool(
        name=name, description=description, strict=False,
        parameters={"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False},
    )


EVENT_ID = {"event_id": {"type": "string", "description": "Event id from scan_live_events, a USGS id (e.g. us7000m9g4), or a SIM- id"}}

SCAN_LIVE = _tool("scan_live_events", "Pull live disaster events (USGS earthquakes past week, GDACS floods/cyclones/volcanoes/wildfires past 30 days) and list which Helix suppliers sit inside each event's impact radius.",
                  {"min_magnitude": {"type": "number", "description": "Minimum earthquake magnitude, default 5.5"}})
GET_EVENT = _tool("get_event", "Fetch a single event by id, including historical USGS earthquakes for replay.", EVENT_ID, ["event_id"])
SIMULATE = _tool("simulate_event", "Create a clearly-labelled what-if earthquake at a location.",
                 {"lat": {"type": "number"}, "lon": {"type": "number"}, "magnitude": {"type": "number"}, "label": {"type": "string"}},
                 ["lat", "lon", "magnitude"])
GET_EXPOSURE = _tool("get_exposure", "Exact exposure calculation for an event: suppliers in radius with distance/zone/downtime, parts with days of cover vs recovery day, products blocked, customer orders at risk, revenue at risk.", EVENT_ID, ["event_id"])
GET_CONTRACTS = _tool("get_contract_terms", "Contract knowledge: supplier force majeure / allocation / expedite cost-sharing terms and customer late-delivery penalties and notification duties.",
                      {"supplier_ids": {"type": "array", "items": {"type": "string"}}, "customers": {"type": "array", "items": {"type": "string"}}})
GET_MITIGATION = _tool("get_mitigation_options", "Mitigation options per at-risk part (wait, air-freight expedite, switch to qualified alternate) with cost, timing, residual gap, the engine's recommended option, and revenue at risk before vs after the plan.", EVENT_ID, ["event_id"])
