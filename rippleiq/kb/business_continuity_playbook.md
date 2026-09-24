# Helix Robotics — Supply Chain Business Continuity Playbook (v3.2)

Owner: Chief Operating Officer · Maintained by: Global Procurement · Classification: Internal

## 1. Purpose
This playbook defines how Helix Robotics detects, assesses and responds to supplier disruptions caused by
natural disasters (earthquakes, floods, tropical cyclones, volcanic eruptions, wildfires). It is the reference
for the RippleIQ war room agents and for every human approver.

## 2. Severity levels
| Level | Trigger | Who is informed | Response time |
|---|---|---|---|
| WATCH | A supplier site is inside an event impact radius but no part has a supply gap | Procurement lead | Next business day |
| HIGH | At least one part has a supply gap; revenue at risk below USD 1,000,000 and no supplier in the severe zone | Head of Procurement, VP Sales | Within 4 hours |
| CRITICAL | Revenue at risk of USD 1,000,000 or more, or any gapped supplier in the severe zone | COO, CFO, VP Sales, Head of Procurement | Within 1 hour, war room convened |

## 3. Spending authority and approval policy
- Mitigation spend up to USD 25,000 per event may be executed by the Procurement lead without further approval.
- Mitigation spend above USD 25,000 per event requires explicit approval by the COO (or the CFO when the COO is unavailable).
- Switching volume to a qualified alternate supplier is allowed only for suppliers listed as qualified alternates in the part master.
- Unqualified suppliers may never be used for safety-relevant parts (force/torque sensors, safety PLC boards, motion control MCUs), regardless of urgency.
- Every approval or rejection must be recorded with the approver name, time and reason.

## 4. Mitigation preference order
1. Use existing inventory and re-sequence production toward strategic customer orders.
2. Air-freight the first post-recovery shipments from the primary supplier when this closes or shrinks the gap.
3. Switch volume to a qualified alternate supplier when the alternate can deliver before the primary recovers.
4. Negotiate partial allocation under the supplier's force majeure allocation clause.
Switching to an alternate supplier that would deliver after the primary has recovered wastes money and must not be recommended.

## 5. Customer communication rules
- Strategic customers (Toyota Tsusho Logistics, Foxconn Line 12, Siemens Healthineers Erlangen, Ocado Robotics Hub) must be notified at least 7 days before an expected delay. Standard customers at least 3 days before.
- Force majeure relief toward customers applies only if notice is given within the contractual window. Late notice means Helix pays the full late-delivery penalty.
- Toyota Tsusho Logistics prefers a phone call from the account director followed by written confirmation.
- Delay notices must state the order number, the cause, the mitigation in progress and the date of the next update. Never promise a recovery date that the mitigation plan does not support.

## 6. Supplier communication rules
- Within 24 hours of a CRITICAL or HIGH event, send each exposed supplier a request for: force majeure status, damage assessment, written recovery plan, and confirmation of the allocation guarantee.
- Tier A suppliers share air-freight cost 50/50 under their contracts; always invoke this clause when expediting from a Tier A supplier.

## 7. Structural risk rules
- Any part with no qualified alternate supplier (single-source) that appears in two or more disruption assessments in 12 months must be escalated to the COO with a second-source qualification proposal.
- Safety stock for parts sourced from Taiwan should cover at least 21 days (target review: Q1).

## 8. Lessons learned from public disruptions
- **2011 Tōhoku earthquake and tsunami (Japan):** a single automotive microcontroller fab in the region stopped and restarted roughly three months later; automakers worldwide lost production because they did not know which of their parts depended on it. Lesson: map sub-tier dependencies before the event.
- **2011 Thailand floods:** industrial estates around Ayutthaya flooded for weeks and disrupted global hard-disk-drive supply. Lesson: floods create long, slow disruptions; treat Orange/Red flood alerts near suppliers as HIGH until proven otherwise.
- **2016 Kumamoto earthquakes (Japan):** damage to component plants in Kumamoto forced Japanese automakers to suspend assembly lines for days. Lesson: single-source sensor suppliers in one region are a structural risk.
- **2021 Suez Canal blockage:** a single grounded ship blocked the canal for about six days and delayed shipments for weeks after. Lesson: transit routes are part of the supply chain; air freight must be pre-contracted.
- **2024 Hualien earthquake (Taiwan):** chipmakers evacuated fabs and restored most operations within days. Lesson: do not over-react with expensive supplier switches when the primary will recover quickly; expedite instead.

## 9. RippleIQ operating principles
- All money, day and quantity figures come from the RippleIQ engine, never from model estimates.
- The impact radius and downtime-by-zone values are heuristics and must be stated as assumptions in every brief.
- Simulated (what-if) events must be labelled SIMULATION in every output.
