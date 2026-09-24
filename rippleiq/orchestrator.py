import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def setup_tracing():
    if os.getenv("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING") != "true":
        return None
    from azure.ai.projects.telemetry import AIProjectInstrumentor
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace
    configure_azure_monitor(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
        disable_logging=True,
        disable_metrics=True,
    )
    AIProjectInstrumentor().instrument()
    return trace.get_tracer("rippleiq")


TRACER = setup_tracing()

import engine  # noqa: E402
from agents import Foundry, parse_json  # noqa: E402
from tools import resolve_event  # noqa: E402

RUNS = ROOT / "runs"
MONEY = re.compile(r"(?:\$\s?(\d[\d,]*(?:\.\d+)?)\s?(million|thousand|[KkMm])?\b|\b(\d[\d,]*(?:\.\d+)?)\s?(million|thousand|[KkMm])?\s?USD\b|\bUSD\s?(\d[\d,]*(?:\.\d+)?))")
MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}


class _NoSpan:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_attribute(self, *a):
        pass


def span(name):
    return TRACER.start_as_current_span(name) if TRACER else _NoSpan()


def say(msg=""):
    print(msg, flush=True)


def _numbers(obj, out):
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    return out


def verify_money(text, assessment):
    allowed = _numbers(assessment, set())
    checked = []
    for m in MONEY.finditer(text):
        num, unit = (m[1], m[2]) if m[1] else (m[3], m[4]) if m[3] else (m[5], None)
        value = float(num.replace(",", "")) * MULT.get((unit or "").lower(), 1)
        ok = any(abs(value - a) <= max(0.01 * abs(a), 500) for a in allowed)
        checked.append({"figure": m[0].strip(), "value": value, "verified": ok})
    return {"figures_checked": len(checked), "verified": sum(c["verified"] for c in checked),
            "unverified": [c["figure"] for c in checked if not c["verified"]]}


def approval_gate(summary, policy):
    if not summary["requires_human_approval"]:
        return {"status": "AUTO_APPROVED", "reason": f"plan cost ${summary['plan_cost_usd']:,} within ${summary['approval_limit_usd']:,} limit"}
    say(f"\n⏸  HUMAN APPROVAL REQUIRED: plan cost ${summary['plan_cost_usd']:,} exceeds ${summary['approval_limit_usd']:,} limit")
    if policy in ("approve", "reject"):
        decision = policy == "approve"
        say(f"   decision supplied by flag: {'APPROVE' if decision else 'REJECT'}")
    else:
        decision = input("   Approve mitigation plan? [y/N] ").strip().lower() == "y"
    return {"status": "APPROVED_BY_HUMAN" if decision else "REJECTED_BY_HUMAN",
            "reason": f"plan cost ${summary['plan_cost_usd']:,} exceeds ${summary['approval_limit_usd']:,} limit",
            "decided_at": datetime.now().isoformat(timespec="seconds")}


def step(f, name, text, record):
    say(f"\n▶ {name} ...")
    with span(f"rippleiq.{name}") as s:
        r = f.run(name, text)
        s.set_attribute("rippleiq.tokens", r["tokens"])
        s.set_attribute("rippleiq.tool_calls", len(r["tool_calls"]))
    say(f"  ✓ {r['seconds']}s · {r['tokens']} tokens · tools: {', '.join(r['tool_calls']) or 'none'}")
    record["steps"].append(r)
    return r


def run(mode_text, approval_policy="ask", deploy=False):
    record = {"started_at": datetime.now().isoformat(timespec="seconds"), "mode": mode_text, "steps": []}
    f = Foundry()
    if deploy:
        say(f"Deploying agents: {f.deploy()}")

    with span("rippleiq.war_room_run") as root:
        root.set_attribute("rippleiq.mode", mode_text)

        signal = step(f, "rippleiq-signal-watcher", mode_text, record)
        sig = parse_json(signal["output"])
        record["signal"] = sig
        say(f"  → {sig.get('title')} · triage={sig.get('triage')} · {sig.get('reason')}")
        if sig.get("triage") != "assess" or not sig.get("selected_event_id"):
            record["outcome"] = "NO_ACTION"
            return _finish(record, f, "No event touches Helix suppliers. Logged, no action.")

        event_id = sig["selected_event_id"]
        assessment = engine.assess(resolve_event(event_id))
        record["assessment_summary"] = assessment["summary"]
        root.set_attribute("rippleiq.event_id", event_id)
        root.set_attribute("rippleiq.severity", assessment["severity"])
        root.set_attribute("rippleiq.revenue_at_risk_usd", assessment["summary"]["revenue_at_risk_usd"])

        exposure = step(f, "rippleiq-exposure-mapper", f"event_id: {event_id}", record)
        exp = parse_json(exposure["output"])
        record["exposure"] = exp
        say(f"  → severity={assessment['severity']} · revenue at risk ${assessment['summary']['revenue_at_risk_usd']:,}")
        if assessment["severity"] in ("none", "watch"):
            record["outcome"] = "WATCH_LIST"
            return _finish(record, f, f"Suppliers in radius but no supply gap. Added to watch list: {', '.join(exp.get('ripple_chain', [])[:2])}")

        impact = step(f, "rippleiq-impact-analyst", json.dumps(exp), record)
        mitigation = step(f, "rippleiq-mitigation-strategist", f"event_id: {event_id}", record)

        record["approval"] = approval_gate(assessment["summary"], approval_policy)
        root.set_attribute("rippleiq.approval", record["approval"]["status"])
        if record["approval"]["status"] != "AUTO_APPROVED" and os.getenv("RIPPLEIQ_MEMORY_ENABLED") == "true":
            s = assessment["summary"]
            try:
                f.remember(f"{datetime.now():%B %Y} war room, {assessment['event']['title']}: mitigation plan costing "
                           f"${s['plan_cost_usd']:,} to cut revenue at risk from ${s['revenue_at_risk_usd']:,} to "
                           f"${s['revenue_at_risk_after_plan_usd']:,} was {record['approval']['status'].replace('_', ' ')}.")
                say("  🧠 decision saved to Foundry memory")
            except Exception as e:
                say(f"  memory write skipped: {str(e)[:80]}")

        brief_input = json.dumps({
            "signal": sig, "exposure": exp, "impact_analysis": impact["output"],
            "mitigation_plan": mitigation["output"], "engine_summary": assessment["summary"],
            "approval": record["approval"], "model_assumptions": assessment["model_assumptions"],
        })
        brief = step(f, "rippleiq-war-room", brief_input, record)
        record["brief"] = brief["output"]
        record["verification"] = verify_money(brief["output"], assessment)
        v = record["verification"]
        root.set_attribute("rippleiq.figures_verified", f"{v['verified']}/{v['figures_checked']}")
        record["outcome"] = record["approval"]["status"]
        return _finish(record, f, brief["output"])


def _finish(record, f, text):
    f.close()
    record["finished_at"] = datetime.now().isoformat(timespec="seconds")
    record["total_tokens"] = sum(s["tokens"] for s in record["steps"])
    record["total_seconds"] = round(sum(s["seconds"] for s in record["steps"]), 1)
    RUNS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RUNS / f"{stamp}.json").write_text(json.dumps(record, indent=2, default=str))
    (RUNS / f"{stamp}.md").write_text(text)
    say("\n" + "=" * 72)
    say(text)
    say("=" * 72)
    if "verification" in record:
        v = record["verification"]
        badge = "all figures verified" if not v["unverified"] else f"unverified: {', '.join(v['unverified'])}"
        say(f"Numbers check: {v['verified']}/{v['figures_checked']} $ figures match the engine · {badge}")
    say(f"Outcome: {record['outcome']} · {record['total_seconds']}s · {record['total_tokens']} tokens · saved runs/{stamp}.json")
    return record


def main():
    p = argparse.ArgumentParser(description="RippleIQ supply chain war room")
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("live")
    r = sub.add_parser("replay")
    r.add_argument("event_id")
    s = sub.add_parser("simulate")
    s.add_argument("lat", type=float)
    s.add_argument("lon", type=float)
    s.add_argument("magnitude", type=float)
    s.add_argument("label", nargs="?", default="What-if scenario")
    sub.add_parser("deploy")
    sub.add_parser("memory")
    for sp in sub.choices.values():
        sp.add_argument("--approve", action="store_true")
        sp.add_argument("--reject", action="store_true")
        sp.add_argument("--deploy", action="store_true")
    a = p.parse_args()

    if a.mode == "memory":
        from agents import MEMORY_SCOPE, MEMORY_STORE
        f = Foundry()
        say(f"🧠 Foundry memory store '{MEMORY_STORE}' · scope '{MEMORY_SCOPE}'\n")
        items = list(f.client.beta.memory_stores.list_memories(MEMORY_STORE, scope=MEMORY_SCOPE))
        for m in items:
            text = " ".join(str(getattr(m, "content", "")).split())
            say(f"  [{getattr(m, 'kind', '')}] {text[:150]}{'…' if len(text) > 150 else ''}")
        kinds = {}
        for m in items:
            kinds[str(getattr(m, "kind", ""))] = kinds.get(str(getattr(m, "kind", "")), 0) + 1
        say(f"\n  {len(items)} memories · " + " · ".join(f"{v} {k}" for k, v in kinds.items()))
        f.close()
        return
    if a.mode == "deploy":
        f = Foundry()
        say(f"Deployed: {f.deploy()}")
        f.close()
        return
    text = {"live": "LIVE", "replay": f"REPLAY {getattr(a, 'event_id', '')}",
            "simulate": f"SIMULATE {getattr(a, 'lat', '')} {getattr(a, 'lon', '')} {getattr(a, 'magnitude', '')} {getattr(a, 'label', '')}"}[a.mode]
    policy = "approve" if a.approve else "reject" if a.reject else "ask"
    run(text, policy, a.deploy)


def flush_traces():
    if TRACER:
        from opentelemetry import trace
        trace.get_tracer_provider().force_flush(15000)


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        flush_traces()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
