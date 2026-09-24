import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
ENV = ROOT / ".env"
load_dotenv(ENV)

from azure.ai.projects.models import (MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions,  # noqa: E402
                                      WorkflowAgentDefinition)

KB_FILES = ["business_continuity_playbook.md", "supplier_contracts.md", "customer_terms.md"]

SEED_MEMORIES = [
    ("user_profile", "COO Aiko Tanaka prefers air-freight expedite from Tier A suppliers over switching volume to an "
                     "alternate supplier whenever the primary supplier recovers before the alternate could deliver."),
    ("chat_summary", "March 2026 war room: a proposal to move harmonic reducer (P03) volume from Taichung Precision Gear "
                     "to Stuttgart Drive Systems was REJECTED by the COO because Stuttgart's delivery would arrive after "
                     "Taichung recovered. The COO approved air freight instead."),
    ("chat_summary", "June 2026 war room: an Orange monsoon flood alert near Kochi put drive wheel treads (P14) from Kochi "
                     "Rubber Works at risk with only 10 days of cover. Chennai Polymer Parts was confirmed as the qualified "
                     "alternate. Toyota Tsusho Logistics asked to be phoned by the account director before any written delay notice."),
    ("user_profile", "Standing procedure: when expediting from a Tier A supplier, always invoke the 50/50 air-freight cost-sharing clause in "
                   "the supplier email and ask for the written recovery plan within 10 days."),
    ("user_profile", "Standing procedure: force/torque sensors (P07) from Kumamoto Sensor Devices are single-source; any disruption touching "
                   "Kumamoto must include a recommendation to fund second-source qualification."),
]


def set_env(key, value):
    lines = [l for l in ENV.read_text().splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n")
    os.environ[key] = value


def ensure_vector_store(f):
    vs_id = os.getenv("RIPPLEIQ_VECTOR_STORE_ID")
    if vs_id:
        try:
            f.openai.vector_stores.retrieve(vs_id)
            print(f"knowledge base: reusing {vs_id}")
            return vs_id
        except Exception:
            pass
    file_ids = []
    for name in KB_FILES:
        with open(ROOT / "kb" / name, "rb") as fh:
            file_ids.append(f.openai.files.create(file=fh, purpose="assistants").id)
    vs = f.openai.vector_stores.create(name="rippleiq-knowledge", file_ids=file_ids)
    for _ in range(60):
        vs = f.openai.vector_stores.retrieve(vs.id)
        if vs.file_counts.in_progress == 0:
            break
        time.sleep(2)
    print(f"knowledge base: {vs.id} files completed={vs.file_counts.completed} failed={vs.file_counts.failed}")
    set_env("RIPPLEIQ_VECTOR_STORE_ID", vs.id)
    return vs.id


def ensure_memory(f, reseed=False):
    from agents import MEMORY_SCOPE, MEMORY_STORE, MINI
    stores = f.client.beta.memory_stores
    existing = {s.name for s in stores.list()}
    if MEMORY_STORE not in existing:
        stores.create(
            name=MEMORY_STORE,
            description="RippleIQ war room decisions, COO preferences and procedures",
            definition=MemoryStoreDefaultDefinition(
                chat_model=MINI, embedding_model=os.getenv("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small"),
                options=MemoryStoreDefaultOptions(user_profile_enabled=True, chat_summary_enabled=True,
                                                  procedural_memory_enabled=True),
            ),
        )
        reseed = True
        print(f"memory store: created {MEMORY_STORE}")
    if reseed:
        try:
            have = {getattr(m, "content", "")[:60] for m in stores.list_memories(MEMORY_STORE, scope=MEMORY_SCOPE)}
            for kind, content in SEED_MEMORIES:
                if content[:60] not in have:
                    stores.create_memory(MEMORY_STORE, scope=MEMORY_SCOPE, content=content, kind=kind)
        except Exception as e:
            print(f"memory store: seeding failed ({str(e)[:120]}...), memory disabled for now")
            set_env("RIPPLEIQ_MEMORY_ENABLED", "false")
            return False
        print(f"memory store: seeded {len(SEED_MEMORIES)} memories")
    else:
        print(f"memory store: reusing {MEMORY_STORE}")
    set_env("RIPPLEIQ_MEMORY_ENABLED", "true")
    return True


def workflow_yaml(name):
    steps = ["rippleiq-signal-watcher", "rippleiq-exposure-mapper", "rippleiq-impact-analyst",
             "rippleiq-mitigation-strategist", "rippleiq-war-room"]
    actions = "".join(
        f"    - kind: InvokeAzureAgent\n"
        f"      id: step_{i + 1}_{s.replace('rippleiq-', '').replace('-', '_')}\n"
        f"      agent:\n"
        f"        name: {s}\n"
        f"      conversationId: =System.ConversationId\n"
        f"      input:\n"
        f'        messages: ""\n'
        f"      output:\n"
        f"        autoSend: true\n"
        for i, s in enumerate(steps)
    )
    return (
        "kind: Workflow\n"
        f"name: {name}\n"
        "description: RippleIQ supply chain war room - signal, exposure, impact, mitigation, executive brief\n"
        "trigger:\n"
        "  kind: OnConversationStart\n"
        "  id: trigger_start\n"
        "  actions:\n"
        f"{actions}"
        "    - kind: EndConversation\n"
        "      id: step_end\n"
    )


def ensure_workflow(f):
    from agents import WORKFLOW_NAME
    wf = f.client.agents.create_version(
        agent_name=WORKFLOW_NAME,
        definition=WorkflowAgentDefinition(workflow=workflow_yaml(WORKFLOW_NAME)),
        description="RippleIQ multi-agent war room workflow",
    )
    print(f"workflow: {wf.name} v{wf.version}")
    set_env("WORKFLOW_AGENT_NAME", wf.name)


def main():
    from agents import Foundry
    f = Foundry()
    ensure_vector_store(f)
    ensure_memory(f, reseed="--reseed" in sys.argv)
    print(f"agents: {f.deploy()}")
    if "--memory-only" not in sys.argv:
        ensure_workflow(f)
    f.close()


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
