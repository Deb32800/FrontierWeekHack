import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "false"

import service  # noqa: E402
from agents import Foundry, parse_json  # noqa: E402

SCENARIOS = [
    ("Hualien 2024 replay", "us7000m9g4"),
    ("Tohoku 2011 replay", "official20110311054624120_30"),
    ("Kumamoto 2016 replay", "us20005iis"),
    ("Chi-Chi 1999 replay", "usp0009eq0"),
    ("Live flood near Kochi", "GDACS-FL-1104121"),
    ("Live Krakatau eruption", "GDACS-VO-1000148"),
    ("Live M6.4 Papua New Guinea", "us7000tiqc"),
    ("Live M6.5 Alaska", "us7000ti1p"),
    ("What-if M7.7 Hsinchu", "SIM-24.80-120.97-M7.7"),
    ("What-if M7.0 Osaka", "SIM-34.69-135.50-M7.0"),
]


class RevenueExact:
    def __call__(self, *, response, revenue_truth):
        got = _field(response, "revenue_at_risk_usd") or 0
        return {"revenue_exact": 1.0 if abs(float(got) - revenue_truth) < 1 else 0.0}


class OrdersExact:
    def __call__(self, *, response, orders_truth):
        got = _field(response, "orders_at_risk") or []
        return {"orders_exact": 1.0 if sorted(o.get("order_id") for o in got) == sorted(orders_truth) else 0.0}


class SeverityMatch:
    def __call__(self, *, response, severity_truth):
        return {"severity_match": 1.0 if _field(response, "severity") == severity_truth else 0.0}


class PenaltyExact:
    def __call__(self, *, response, penalty_truth):
        got = _field(response, "penalty_exposure_usd")
        if got is None and penalty_truth == 0:
            return {"penalty_exact": 1.0}
        return {"penalty_exact": 1.0 if got is not None and abs(float(got) - penalty_truth) < 1 else 0.0}


def _field(response, key):
    try:
        return parse_json(response).get(key)
    except Exception:
        return None


def collect():
    f = Foundry()
    rows = []
    for label, event_id in SCENARIOS:
        truth = service.get_exposure(event_id)
        r = f.run("rippleiq-exposure-mapper", f"event_id: {event_id}")
        rows.append({
            "query": f"event_id: {event_id}", "scenario": label, "response": r["output"],
            "revenue_truth": truth["summary"]["revenue_at_risk_usd"],
            "penalty_truth": truth["summary"]["penalty_exposure_usd"],
            "orders_truth": [o["order_id"] for o in truth["orders_at_risk"]],
            "severity_truth": truth["severity"], "tokens": r["tokens"], "seconds": r["seconds"],
        })
        print(f"{label:28} truth=${truth['summary']['revenue_at_risk_usd']:>9,} severity={truth['severity']:8} "
              f"agent={_field(r['output'], 'revenue_at_risk_usd')} {_field(r['output'], 'severity')} · {r['tokens']} tok", flush=True)
    f.close()
    (HERE / "exposure_eval.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def judge_config():
    from azure.ai.evaluation import AzureOpenAIModelConfiguration
    key = subprocess.run(["az", "cognitiveservices", "account", "keys", "list", "-n", os.environ["FOUNDRY_RESOURCE_NAME"],
                          "-g", os.environ["RESOURCE_GROUP"], "--query", "key1", "-o", "tsv"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return AzureOpenAIModelConfiguration(azure_endpoint=os.environ["FOUNDRY_ENDPOINT"], api_key=key,
                                         azure_deployment=os.environ["MINI_DEPLOYMENT_NAME"], api_version="2025-04-01-preview")


def score():
    from azure.ai.evaluation import CoherenceEvaluator, evaluate
    result = evaluate(
        data=str(HERE / "exposure_eval.jsonl"),
        evaluation_name="rippleiq-exposure-accuracy",
        evaluators={
            "revenue": RevenueExact(), "orders": OrdersExact(), "severity": SeverityMatch(), "penalty": PenaltyExact(),
            "coherence": CoherenceEvaluator(model_config=judge_config(), is_reasoning_model=True),
        },
        evaluator_config={"coherence": {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}}},
        azure_ai_project=os.environ["PROJECT_CONNECTION_STRING"],
        output_path=str(HERE / "exposure_eval_results.json"),
    )
    print(json.dumps(result["metrics"], indent=2))
    if result.get("studio_url"):
        print("Foundry evaluation:", result["studio_url"])


if __name__ == "__main__":
    if "--score-only" not in sys.argv:
        collect()
    score()
    sys.stdout.flush()
    os._exit(0)
