import json
import random
from pathlib import Path

OUT = Path(__file__).parent
random.seed(42)

COMPANY = {
    "name": "Helix Robotics",
    "hq": {"city": "Osaka", "country": "Japan", "lat": 34.6937, "lon": 135.5023},
    "industry": "Collaborative robots and autonomous mobile robots",
    "approval_limit_usd": 25000,
}

SUPPLIERS = [
    ("S01", "Formosa Semicon", "Hsinchu", "Taiwan", 24.8066, 120.9686, 5, "A"),
    ("S02", "Taichung Precision Gear", "Taichung", "Taiwan", 24.1477, 120.6736, 5, "A"),
    ("S03", "Yilan Opto", "Yilan", "Taiwan", 24.7570, 121.7530, 5, "B"),
    ("S04", "Kansai Servo Works", "Higashiosaka", "Japan", 34.6795, 135.6008, 1, "A"),
    ("S05", "Sendai Capacitor", "Sendai", "Japan", 38.2682, 140.8694, 2, "B"),
    ("S06", "Kumamoto Sensor Devices", "Kumamoto", "Japan", 32.8031, 130.7079, 2, "A"),
    ("S07", "Busan Energy Cells", "Busan", "South Korea", 35.1796, 129.0756, 3, "A"),
    ("S08", "Shenzhen Harness Co", "Shenzhen", "China", 22.5431, 114.0579, 6, "B"),
    ("S09", "Suzhou Castings", "Suzhou", "China", 31.2990, 120.5853, 5, "B"),
    ("S10", "Chengdu Magnetics", "Chengdu", "China", 30.5728, 104.0668, 8, "A"),
    ("S11", "Penang Microsystems", "Penang", "Malaysia", 5.4164, 100.3327, 9, "A"),
    ("S12", "Ayutthaya Motor Tech", "Ayutthaya", "Thailand", 14.3532, 100.5689, 9, "B"),
    ("S13", "Hanoi PCB Assembly", "Hanoi", "Vietnam", 21.0285, 105.8542, 7, "B"),
    ("S14", "Stuttgart Drive Systems", "Stuttgart", "Germany", 48.7758, 9.1829, 21, "A"),
    ("S15", "Monterrey Metals", "Monterrey", "Mexico", 25.6866, -100.3161, 24, "B"),
    ("S16", "Austin Lidar Labs", "Austin", "USA", 30.2672, -97.7431, 14, "A"),
    ("S17", "Kochi Rubber Works", "Kochi", "India", 9.9312, 76.2673, 12, "B"),
    ("S18", "Banten Steel Sheet", "Cilegon", "Indonesia", -6.0025, 106.0111, 8, "B"),
    ("S19", "Kaohsiung Cell Pack", "Kaohsiung", "Taiwan", 22.6273, 120.3014, 5, "B"),
    ("S20", "Chennai Polymer Parts", "Chennai", "India", 13.0827, 80.2707, 12, "B"),
]

# part_id, name, primary, [alternates], unit_cost_usd, target_days_of_cover, lead_time_days
PARTS = [
    ("P01", "Motion control MCU", "S01", ["S11"], 18.5, 18, 42),
    ("P02", "Motor driver IC", "S01", ["S11"], 6.2, 24, 42),
    ("P03", "Harmonic reducer", "S02", ["S14"], 410.0, 12, 56),
    ("P04", "Depth camera module", "S03", [], 145.0, 16, 35),
    ("P05", "Servo motor 400W", "S04", ["S12"], 220.0, 20, 21),
    ("P06", "Aluminium capacitor bank", "S05", ["S13"], 9.8, 30, 28),
    ("P07", "Force/torque sensor", "S06", [], 380.0, 14, 45),
    ("P08", "Li-ion battery pack 48V", "S07", ["S19"], 690.0, 25, 30),
    ("P09", "Cable harness set", "S08", ["S13"], 34.0, 35, 25),
    ("P10", "Cast aluminium arm link", "S09", ["S15"], 95.0, 22, 35),
    ("P11", "NdFeB magnet set", "S10", [], 52.0, 15, 40),
    ("P12", "Safety PLC board", "S13", ["S11"], 120.0, 28, 30),
    ("P13", "Lidar unit", "S16", [], 1250.0, 40, 42),
    ("P14", "Drive wheel tread", "S17", ["S20"], 22.0, 10, 30),
    ("P15", "Steel chassis sheet", "S18", ["S15"], 64.0, 18, 28),
    ("P16", "Gripper finger actuator", "S12", ["S04"], 75.0, 26, 21),
    ("P17", "Encoder chip", "S06", ["S11"], 11.0, 30, 45),
    ("P18", "Vision SoC", "S01", [], 88.0, 20, 49),
]

PRODUCTS = [
    ("HX-C7", "HX-Cobot 7 collaborative arm", 38000, 14,
     {"P01": 6, "P02": 12, "P03": 6, "P05": 6, "P06": 8, "P07": 1, "P09": 1, "P10": 6, "P11": 6, "P12": 1, "P17": 6}),
    ("HX-A300", "HX-AMR 300 mobile robot", 52000, 6,
     {"P01": 2, "P02": 4, "P04": 2, "P06": 6, "P08": 1, "P09": 1, "P11": 4, "P12": 1, "P13": 1, "P14": 4, "P15": 4, "P18": 1}),
    ("HX-VK", "HX-Vision Kit", 9500, 10,
     {"P04": 1, "P09": 1, "P18": 1}),
    ("HX-GP", "HX-Gripper Pro", 4200, 20,
     {"P01": 1, "P02": 2, "P16": 2, "P17": 2, "P06": 2}),
]

CUSTOMERS = [
    "Toyota Tsusho Logistics", "Nordic Pharma Packaging", "Samsung Display Tooling",
    "Bosch Rexroth Assembly", "Walmart DC Dallas", "Maersk Warehousing Rotterdam",
    "Panasonic Energy Kobe", "Foxconn Line 12", "Unilever Lipton Plant",
    "Siemens Healthineers Erlangen", "Ocado Robotics Hub", "Tata Motors Pune",
]
STRATEGIC = {"Foxconn Line 12", "Toyota Tsusho Logistics", "Siemens Healthineers Erlangen", "Ocado Robotics Hub"}


def build_orders():
    orders = []
    n = 1
    for sku, _, price, _, _ in PRODUCTS:
        for _ in range(9):
            qty = random.choice([2, 4, 5, 8, 10, 12, 20]) if price < 20000 else random.choice([1, 2, 3, 4, 6])
            customer = random.choice(CUSTOMERS)
            orders.append({
                "order_id": f"SO-{2400 + n}",
                "customer": customer,
                "product_id": sku,
                "qty": qty,
                "unit_price_usd": price,
                "value_usd": qty * price,
                "due_in_days": random.randint(3, 75),
                "priority": "strategic" if customer in STRATEGIC else "standard",
            })
            n += 1
    return sorted(orders, key=lambda o: o["due_in_days"])


def build_contracts(suppliers):
    contracts = {"suppliers": [], "customers": []}
    for s in suppliers:
        tier_a = s["reliability_tier"] == "A"
        contracts["suppliers"].append({
            "supplier_id": s["supplier_id"],
            "supplier": s["name"],
            "force_majeure_notice_days": 3 if tier_a else 7,
            "force_majeure_clause": (
                f"{s['name']} shall notify Helix within {3 if tier_a else 7} days of any force majeure event "
                "and provide a written recovery plan within 10 days. During shortage, allocation to Helix "
                f"shall be no less than {'pro-rata share of' if tier_a else '50% of'} pre-event volume."
            ),
            "allocation_guarantee": "pro-rata" if tier_a else "50% of pre-event volume",
            "expedite_cost_sharing": "50/50 split on air freight" if tier_a else "Helix pays 100%",
            "business_continuity_plan_on_file": tier_a,
            "backup_site": random.choice(["none", "same region", "other country"]) if tier_a else "none",
        })
    for c in CUSTOMERS:
        strategic = c in STRATEGIC
        contracts["customers"].append({
            "customer": c,
            "late_delivery_penalty_pct_per_week": 2.0 if strategic else 0.5,
            "penalty_cap_pct": 10 if strategic else 5,
            "notification_required_days": 7 if strategic else 3,
            "clause": (
                f"Late delivery incurs {2.0 if strategic else 0.5}% of order value per week, capped at "
                f"{10 if strategic else 5}%. Helix must notify {c} at least {7 if strategic else 3} days "
                "before any expected delay; force majeure relief applies only if notice is given."
            ),
        })
    return contracts


def main():
    suppliers = [
        {"supplier_id": s[0], "name": s[1], "city": s[2], "country": s[3], "lat": s[4], "lon": s[5],
         "transit_days_to_osaka": s[6], "reliability_tier": s[7]}
        for s in SUPPLIERS
    ]
    products = [
        {"product_id": p[0], "name": p[1], "unit_price_usd": p[2], "units_per_day": p[3] / 7, "bom": p[4]}
        for p in PRODUCTS
    ]
    parts = []
    for p in PARTS:
        daily = sum(prod["bom"].get(p[0], 0) * prod["units_per_day"] for prod in products)
        on_hand = round(daily * p[5])
        parts.append({
            "part_id": p[0], "name": p[1], "primary_supplier": p[2], "qualified_alternates": p[3],
            "unit_cost_usd": p[4], "on_hand_units": on_hand, "lead_time_days": p[6],
            "daily_usage_units": round(daily, 2),
            "days_of_cover": round(on_hand / daily, 1),
        })
    for prod in products:
        prod["units_per_day"] = round(prod["units_per_day"], 2)

    files = {
        "company.json": COMPANY,
        "suppliers.json": suppliers,
        "parts.json": parts,
        "products.json": products,
        "orders.json": build_orders(),
        "contracts.json": build_contracts(suppliers),
    }
    for name, payload in files.items():
        (OUT / name).write_text(json.dumps(payload, indent=2))
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
