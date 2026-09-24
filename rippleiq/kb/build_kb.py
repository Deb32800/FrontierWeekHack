import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"


def main():
    contracts = json.loads((DATA / "contracts.json").read_text())
    suppliers = {s["supplier_id"]: s for s in json.loads((DATA / "suppliers.json").read_text())}
    parts = json.loads((DATA / "parts.json").read_text())

    lines = ["# Helix Robotics — Supplier Contract Register", "",
             "Key contractual terms for every direct-material supplier. Source: Legal & Procurement.", ""]
    for c in contracts["suppliers"]:
        s = suppliers[c["supplier_id"]]
        supplied = [f"{p['part_id']} {p['name']}" for p in parts if p["primary_supplier"] == c["supplier_id"]]
        alt_for = [f"{p['part_id']} {p['name']}" for p in parts if c["supplier_id"] in p["qualified_alternates"]]
        lines += [
            f"## {c['supplier_id']} — {c['supplier']} ({s['city']}, {s['country']})",
            f"- Reliability tier: {s['reliability_tier']}",
            f"- Primary supplier for: {', '.join(supplied) or 'none'}",
            f"- Qualified alternate for: {', '.join(alt_for) or 'none'}",
            f"- Force majeure clause: {c['force_majeure_clause']}",
            f"- Allocation guarantee during shortage: {c['allocation_guarantee']}",
            f"- Expedite cost sharing: {c['expedite_cost_sharing']}",
            f"- Business continuity plan on file: {'yes' if c['business_continuity_plan_on_file'] else 'no'}",
            f"- Backup production site: {c['backup_site']}",
            "",
        ]
    (HERE / "supplier_contracts.md").write_text("\n".join(lines))

    lines = ["# Helix Robotics — Customer Delivery Terms", "",
             "Late-delivery penalties and delay-notification duties per customer. Source: Sales Operations.", ""]
    for c in contracts["customers"]:
        tier = "Strategic account" if c["late_delivery_penalty_pct_per_week"] >= 2 else "Standard account"
        lines += [
            f"## {c['customer']}",
            f"- Account tier: {tier}",
            f"- Late-delivery penalty: {c['late_delivery_penalty_pct_per_week']}% of order value per week, capped at {c['penalty_cap_pct']}%",
            f"- Delay notification required: at least {c['notification_required_days']} days before the expected delay",
            f"- Clause: {c['clause']}",
            "",
        ]
    (HERE / "customer_terms.md").write_text("\n".join(lines))
    print("wrote supplier_contracts.md, customer_terms.md")


if __name__ == "__main__":
    main()
