import json

import azure.functions as func

import service

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _ok(payload):
    return func.HttpResponse(json.dumps(payload, default=str), mimetype="application/json")


def _guard(fn):
    def wrapper(req: func.HttpRequest) -> func.HttpResponse:
        try:
            return _ok(fn(req))
        except Exception as e:
            return func.HttpResponse(json.dumps({"error": f"{type(e).__name__}: {e}"}), status_code=400, mimetype="application/json")
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route(route="health", methods=["GET"])
@_guard
def health(req):
    return {"status": "ok", "service": "rippleiq-engine"}


@app.route(route="events/live", methods=["GET"])
@_guard
def events_live(req):
    return service.scan_live_events(req.params.get("min_magnitude", 5.5))


@app.route(route="events/{event_id}", methods=["GET"])
@_guard
def event_get(req):
    return service.get_event(req.route_params["event_id"])


@app.route(route="simulate", methods=["GET"])
@_guard
def simulate(req):
    p = req.params
    return service.simulate_event(p["lat"], p["lon"], p["magnitude"], p.get("label", "What-if scenario"))


@app.route(route="exposure/{event_id}", methods=["GET"])
@_guard
def exposure(req):
    return service.get_exposure(req.route_params["event_id"])


@app.route(route="mitigation/{event_id}", methods=["GET"])
@_guard
def mitigation(req):
    return service.get_mitigation_options(req.route_params["event_id"])


@app.route(route="contracts", methods=["GET"])
@_guard
def contracts(req):
    return service.get_contract_terms(req.params.get("supplier_ids"), req.params.get("customers"))
