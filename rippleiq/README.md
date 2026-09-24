# RippleIQ — Supply Chain War Room on Microsoft Foundry

> See the ripple before it hits.

RippleIQ turns a live disaster alert (earthquake, flood, cyclone, volcano) into an exact, approved supply-chain
recovery plan in about a minute. Five specialised agents on Microsoft Foundry map which suppliers, parts, products
and customer orders are hit, read the contracts, compare mitigation options, and brief the COO. Any plan above the
spending limit waits for a human decision, and that decision is remembered.

Built for the Microsoft Agent-a-thon, Level 3 Architect track.

## How it works

```
Live USGS / GDACS feeds ──► RippleIQ Engine API (Azure Functions, exact math)
                                   ▲ OpenAPI tool
Microsoft Foundry workflow ────────┘
  1 Signal Watcher        gpt-5.4-mini  OpenAPI: live events / replay / simulate
  2 Exposure Mapper       gpt-5.4-mini  OpenAPI: exact exposure
  3 Impact Analyst        gpt-5.4       File Search: contracts, SLAs, continuity playbook
  4 Mitigation Strategist gpt-5.4       OpenAPI: mitigation options
  ⏸ Approval gate (> $25,000 → COO)     decision written to Foundry memory
  5 War Room              gpt-5.4       File Search + Memory → executive brief
Governance: dollar verifier · audit log per run · App Insights traces · Foundry evaluations
```

## Results (synthetic company, real disaster data)

| Event | Revenue at risk | After plan | Plan cost |
|---|---|---|---|
| Tōhoku 2011 (M9.1) | $1,603,400 | $0 | $23,291 |
| Flood near Kochi, India (live GDACS) | $312,000 | $0 | $453 |
| Chi-Chi 1999 (M7.7) | $218,000 | $114,000 | $34,118 |
| Hualien 2024 (M7.4) | $142,000 | $38,000 | $34,118 (COO approval) |

Foundry evaluation on 10 scenarios (4 historical, 4 live, 2 what-if): 100% exact revenue, orders, severity and
penalties; coherence 3.9/5. Full war-room run: 18/18 dollar figures in the brief verified against the engine.

## Repository layout

| Path | Purpose |
|---|---|
| `engine.py` | Exact exposure, impact, penalty and mitigation math; USGS/GDACS clients; what-if simulator |
| `service.py` | Tool functions shared by the local tools and the cloud API |
| `api/` | Azure Functions app exposing the engine as a REST API |
| `agents.py` | The five Foundry agent definitions and runner |
| `orchestrator.py` | CLI war room: branching, approval gate, dollar verifier, memory write-back, tracing, audit log |
| `setup_foundry.py` | Creates the knowledge base, memory store, agents and workflow |
| `kb/` | Knowledge base documents (continuity playbook, supplier contracts, customer terms) |
| `data/` | Synthetic Helix Robotics data (`build_data.py` regenerates it) |
| `eval/` | Evaluation dataset builder and Foundry evaluation run |
| `infra/` | `deploy.sh` (Foundry, models, App Insights) and `deploy_api.sh` (engine API) |

## Run it

```bash
python3.12 -m venv ../.venv && source ../.venv/bin/activate
pip install -r ../requirements.txt requests
az login
bash infra/deploy.sh          # Foundry project, gpt-5.4, gpt-5.4-mini, App Insights -> .env
bash infra/deploy_api.sh      # RippleIQ Engine API on Azure Functions -> .env
python setup_foundry.py --reseed

python orchestrator.py live                       # scan live disasters now
python orchestrator.py replay us7000m9g4          # Hualien 2024 (asks for COO approval)
python orchestrator.py simulate 24.8 120.97 7.7 "M7.7 near Hsinchu"
python orchestrator.py memory                     # what the war room remembers
python eval/run_eval.py                           # evaluation, logged to Foundry
```

The workflow `rippleiq-war-room-workflow` also runs in the Foundry portal: Build → Agents → open the workflow →
Preview, then type `LIVE` or `REPLAY us7000m9g4`.

## Honest limits

- Impact radius and downtime per zone are heuristics, stated in every brief.
- Company, contract and order data are synthetic; disaster data is real.
- Only first-tier suppliers are mapped. The demo engine API allows anonymous access.
