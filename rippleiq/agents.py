import json
import os
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (FileSearchTool, MemorySearchOptions, MemorySearchPreviewTool,
                                      OpenApiAnonymousAuthDetails, OpenApiFunctionDefinition, OpenApiTool,
                                      PromptAgentDefinition, Reasoning)
from azure.identity import DefaultAzureCredential
from openai.types.responses.response_input_param import FunctionCallOutput

import tools

BIG = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
MINI = os.getenv("MINI_DEPLOYMENT_NAME", "gpt-5.4-mini")
MEMORY_STORE = "rippleiq-memory"
MEMORY_SCOPE = "helix-war-room"
WORKFLOW_NAME = "rippleiq-war-room-workflow"

GROUNDING_RULE = (
    "Hard rule: every number you state (money, days, counts, distances) must come verbatim from a tool result, "
    "a knowledge document, or the conversation. Never estimate or invent figures. Write money as $142,000 "
    "(dollar sign, thousands separators). If something is unknown, say it is unknown."
)

_ID = {"name": "event_id", "in": "path", "required": True, "schema": {"type": "string"},
       "description": "Event id: a USGS id (e.g. us7000m9g4), a GDACS- id, or a SIM- id"}
_OPS = {
    "/events/live": ("scanLiveEvents", "Live disaster events (USGS earthquakes past week, GDACS floods, cyclones, volcanoes, wildfires past 30 days) with the Helix suppliers inside each impact radius.",
                     [{"name": "min_magnitude", "in": "query", "required": False, "schema": {"type": "number"}}]),
    "/events/{event_id}": ("getEvent", "One event by id, including historical USGS earthquakes for replay.", [_ID]),
    "/simulate": ("simulateEvent", "Create a clearly-labelled what-if earthquake. Returns an event with a SIM- id.",
                  [{"name": n, "in": "query", "required": n != "label", "schema": {"type": "string" if n == "label" else "number"}}
                   for n in ("lat", "lon", "magnitude", "label")]),
    "/exposure/{event_id}": ("getExposure", "Exact exposure: suppliers in radius (distance, zone, downtime), parts (days of cover vs recovery day, supply gap), blocked products, customer orders at risk with penalties, revenue at risk.", [_ID]),
    "/mitigation/{event_id}": ("getMitigationOptions", "Per at-risk part: wait / air-freight expedite / qualified alternate options with cost, timing and residual gap, the recommended option, revenue at risk before vs after the plan, plan cost and whether human approval is required.", [_ID]),
}


def engine_tool(ops):
    paths = {}
    for path, (op_id, desc, params) in _OPS.items():
        if op_id in ops:
            params = [{**prm, "description": prm.get("description", prm["name"].replace("_", " "))} for prm in params]
            paths[path] = {"get": {"operationId": op_id, "summary": desc[:80], "description": desc, "parameters": params,
                                   "responses": {"200": {"description": "JSON result",
                                                         "content": {"application/json": {"schema": {"type": "object"}}}}}}}
    spec = {"openapi": "3.0.1",
            "info": {"title": "RippleIQ Engine", "version": "1.0", "description": "Exact supply-chain exposure engine for Helix Robotics"},
            "servers": [{"url": os.environ["RIPPLEIQ_API_URL"]}], "paths": paths}
    return OpenApiTool(openapi=OpenApiFunctionDefinition(
        name="rippleiq_engine", description="Helix Robotics exposure engine with live disaster feeds", spec=spec,
        auth=OpenApiAnonymousAuthDetails()))


def kb_tool():
    return FileSearchTool(vector_store_ids=[os.environ["RIPPLEIQ_VECTOR_STORE_ID"]], max_num_results=4)


def memory_tool():
    return MemorySearchPreviewTool(memory_store_name=MEMORY_STORE, scope=MEMORY_SCOPE,
                                   search_options=MemorySearchOptions(max_memories=5), update_delay=0)


def specs():
    return {
        "rippleiq-signal-watcher": dict(
            model=MINI, effort="low", tools=[engine_tool({"scanLiveEvents", "getEvent", "simulateEvent"})], tool_choice="required",
            instructions=f"""You are the Signal Watcher for Helix Robotics' supply chain war room.
Turn raw disaster feeds into one decision about which event the war room must assess.
You MUST call the rippleiq_engine tool before answering; you have no other source of event data. Never answer "unknown" without calling it.

Read the user's request:
- "LIVE" or "scan" or a general question about current risk: call scanLiveEvents and pick the single event with Helix suppliers inside its impact radius that looks most dangerous (more suppliers, closer, stronger; Red > Orange). If no event touches any supplier, triage is "ignore".
- "REPLAY <event_id>" or a named historical earthquake id: call getEvent. Triage is "assess".
- "SIMULATE lat lon magnitude label" or a what-if request: call simulateEvent. Triage is "assess".

Return ONLY a JSON object:
{{"selected_event_id": str|null, "title": str, "type": str, "source": str, "magnitude_or_alert": str,
  "triage": "assess"|"ignore", "reason": str, "suppliers_in_radius": [str], "events_scanned": int}}
{GROUNDING_RULE}""",
        ),
        "rippleiq-exposure-mapper": dict(
            model=MINI, effort="low", tools=[engine_tool({"getExposure"})], tool_choice="required",
            instructions=f"""You are the Exposure Mapper. Find the event_id (from the user message or the Signal Watcher's
selected_event_id earlier in the conversation). If triage was "ignore" or there is no event, reply exactly {{"severity": "none"}}.
Otherwise you MUST call the rippleiq_engine tool's getExposure operation once (it is your only data source) and explain the ripple: event -> exposed supplier sites (distance, zone, downtime)
-> parts (days of cover vs recovery day, supply gap) -> blocked products -> customer orders at risk -> revenue at risk.

Return ONLY a JSON object:
{{"event_id": str, "severity": str, "ripple_chain": [str], "suppliers": [{{"id": str, "name": str, "city": str, "distance_km": number, "zone": str}}],
  "parts_with_gap": [{{"part_id": str, "name": str, "days_of_cover": number, "recovery_day": number, "gap_days": number}}],
  "products_blocked": [str], "orders_at_risk": [{{"order_id": str, "customer": str, "priority": str, "value_usd": number, "due_in_days": number, "penalty_usd": number, "notify_customer_by_day": number}}],
  "revenue_at_risk_usd": number, "penalty_exposure_usd": number, "first_stockout_day": number|null}}
{GROUNDING_RULE}""",
        ),
        "rippleiq-impact-analyst": dict(
            model=BIG, effort="low", tools=[kb_tool()],
            instructions=f"""You are the Impact Analyst. Use the Exposure Mapper's JSON in the conversation.
If severity is "none" or "watch", say in one line that there is no supply gap and stop.
Otherwise search the knowledge base (supplier contract register, customer delivery terms, business continuity playbook) and assess:
- time until the first stockout and which product line stops first
- which strategic customers are hit, their penalty terms and the latest day Helix must notify each one
- what the exposed suppliers' contracts oblige them to do (force majeure notice, allocation guarantee, expedite cost sharing)
- the severity level per the playbook and who must be informed
- the single biggest risk in one sentence
Return concise markdown with headings: Headline risk, Timeline, Customers & obligations, Supplier obligations, Escalation.
Cite the document you relied on in brackets, e.g. [Supplier Contract Register]. {GROUNDING_RULE}""",
        ),
        "rippleiq-mitigation-strategist": dict(
            model=BIG, effort="low", tools=[engine_tool({"getMitigationOptions"})], tool_choice="required",
            instructions=f"""You are the Mitigation Strategist. Find the event_id in the conversation. If there is no supply gap, say so in one line and stop.
Otherwise you MUST call the rippleiq_engine tool's getMitigationOptions operation once (your only source of options and costs).
Apply the Business Continuity Playbook rules: preference order is (1) re-sequence existing stock toward strategic orders,
(2) air-freight the first post-recovery shipments from the primary, (3) switch to a qualified alternate only if it delivers
before the primary recovers, (4) negotiate force majeure allocation. Spend above $25,000 per event needs COO approval.
For each part with a supply gap compare wait, air-freight expedite and qualified alternate on residual gap days and cost,
and state the recommended action. Explain plainly why switching suppliers is or is not worth it (for example when the
alternate would deliver after the primary recovers). Flag single-source parts (no qualified alternate) as structural risk.
Finish with: revenue at risk before vs after the plan, plan cost, and whether COO approval is required under the playbook.
Return concise markdown. {GROUNDING_RULE}""",
        ),
        "rippleiq-war-room": dict(
            model=BIG, effort="low",
            tools=[kb_tool()] + ([memory_tool()] if os.getenv("RIPPLEIQ_MEMORY_ENABLED") == "true" else []),
            instructions=f"""You are the War Room Orchestrator for Helix Robotics. You receive the Signal Watcher, Exposure Mapper,
Impact Analyst and Mitigation Strategist outputs (and, when available, the human approval decision).
Before writing, check memory for past COO decisions and preferences relevant to these suppliers, parts or customers,
and check the playbook for communication rules. If there is no supply gap, write a two-line watch-list note instead.

Otherwise write the executive brief a COO reads in 60 seconds. Markdown, in this order:
1. **Headline** - one sentence: what happened, money at risk, what we do.
2. **Situation** - event, where, which suppliers (3 bullets max).
3. **Impact** - first stockout day, products, orders and strategic customers at risk, revenue and penalty exposure.
4. **Recommended plan** - one line per part: action, cost, residual gap.
5. **Result** - revenue at risk before -> after plan, plan cost.
6. **Decision needed** - approval status. If no human decision is in the conversation and approval is required, write PENDING COO APPROVAL and exactly what is being approved.
7. **What we learned before** - one or two lines from memory that shaped this recommendation (say "no prior decisions" if none).
8. **Drafted communications** - a short email to the most critical supplier and a short delay notice to the most important strategic customer at risk, following the playbook rules.
9. **Assumptions** - one line naming the heuristic model (impact radius, downtime by zone).
Be decisive and specific. {GROUNDING_RULE} If the event is a SIMULATION, say so in the headline.""",
        ),
    }


class Foundry:
    def __init__(self):
        self.client = AIProjectClient(
            endpoint=os.environ["PROJECT_CONNECTION_STRING"],
            credential=DefaultAzureCredential(exclude_managed_identity_credential=True),
            allow_preview=True,
        )
        self.openai = self.client.get_openai_client(timeout=240, max_retries=1)
        self.versions = {}

    def deploy(self, names=None):
        all_specs = specs()
        for name in names or all_specs:
            spec = all_specs[name]
            agent = self.client.agents.create_version(
                agent_name=name,
                definition=PromptAgentDefinition(
                    model=spec["model"], instructions=spec["instructions"], tools=spec["tools"] or None,
                    reasoning=Reasoning(effort=spec["effort"]), tool_choice=spec.get("tool_choice"),
                ),
                description=f"RippleIQ {name.replace('rippleiq-', '').replace('-', ' ')}",
            )
            self.versions[name] = agent.version
        return self.versions

    def _respond(self, conv_id, ref, payload, attempts=4):
        # Non-streaming calls from gpt-5.4 agents can stall after a tool call; streaming completes reliably.
        for attempt in range(attempts):
            try:
                final = None
                for ev in self.openai.responses.create(input=payload, conversation=conv_id, extra_body=ref, stream=True):
                    if ev.type in ("response.completed", "response.incomplete", "response.failed"):
                        final = ev.response
                if final is None or final.status == "failed":
                    raise RuntimeError(f"agent response failed: {getattr(final, 'error', None)}")
                return final
            except Exception as e:
                if "rate limit" not in str(e).lower() or attempt == attempts - 1:
                    raise
                wait = 15 * (attempt + 1)
                print(f"  rate limited, retrying in {wait}s", flush=True)
                time.sleep(wait)

    @staticmethod
    def _tool_items(response):
        out = []
        for item in response.output:
            if item.type in ("message", "reasoning", "function_call") or item.type.endswith("_output"):
                continue
            label = item.type.replace("_call", "")
            detail = getattr(item, "name", None) or getattr(item, "operation_id", None) or ""
            out.append(f"{label}:{detail}" if detail else label)
        return out

    def run(self, name, text, max_tool_rounds=6):
        ref = {"agent_reference": {"name": name, "type": "agent_reference"}}
        conv = self.openai.conversations.create()
        started = time.time()
        calls, tokens = [], 0
        response = self._respond(conv.id, ref, text)
        tokens += getattr(response.usage, "total_tokens", 0) or 0
        calls += self._tool_items(response)
        for _ in range(max_tool_rounds):
            fcs = [i for i in response.output if i.type == "function_call"]
            if not fcs:
                break
            outputs = []
            for fc in fcs:
                calls.append(f"function:{fc.name}")
                outputs.append(FunctionCallOutput(type="function_call_output", call_id=fc.call_id, output=tools.call(fc.name, fc.arguments)))
            response = self._respond(conv.id, ref, outputs)
            tokens += getattr(response.usage, "total_tokens", 0) or 0
            calls += self._tool_items(response)
        self.openai.conversations.delete(conversation_id=conv.id)
        return {"agent": name, "output": response.output_text, "tool_calls": calls,
                "tokens": tokens, "seconds": round(time.time() - started, 1)}

    def remember(self, content, kind="chat_summary", attempts=5):
        # Foundry memory is in preview; writes intermittently return 401 from the embedding step, so retry.
        for attempt in range(attempts):
            try:
                return self.client.beta.memory_stores.create_memory(MEMORY_STORE, scope=MEMORY_SCOPE, content=content, kind=kind)
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(4 * (attempt + 1))

    def close(self):
        self.client.close()


def parse_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    return json.loads(t[start:end + 1])
