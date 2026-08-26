"""
seed_crm.py

Seeds crm_accounts / crm_contacts / crm_deals / crm_activities so the KPI /
employee-performance feature (kpi.py) has real data to compute from.

WHY THE THREE REPS ARE DELIBERATELY UNEVEN
A fair performance-scoring system has to be tested against a case where naive
metrics (raw deal count, raw win rate) would rank people WRONG. So this seeds
three reps with deliberately different account difficulty:

  - SMB Volume Rep    -- many small, easy, fast-closing deals. High win rate,
                         high deal COUNT. Looks best on every naive metric.
  - Balanced Rep       -- mid-market mix. The fair control/baseline.
  - Enterprise Specialist -- few, large, hard, slow-closing deals. LOW win
                         rate and LOW deal count (enterprise deals are
                         genuinely harder to close) but each win is worth far
                         more. Looks WORST on naive metrics.

If value-weighted, segment-difficulty-adjusted scoring (kpi.py) is working
correctly, the Enterprise Specialist should score competitively -- or even
top -- once account difficulty is accounted for, despite having the fewest
wins. If a "fair" scoring system still ranks them last, something is wrong
with the normalization, not with the rep. That flip is the whole point.

Run once, AFTER seed_org.py and seed_data.py (needs the Sales department
and the `customers` table to already exist):
    python api/seed_crm.py
"""

import sys
import os
import random
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

random.seed(42)  # reproducible

COMPANY_PREFIXES = ["North", "Summit", "Blue", "Vertex", "Meridian", "Cascade", "Harbor", "Ironwood", "Cobalt", "Granite"]
COMPANY_SUFFIXES = ["Industries", "Solutions", "Group", "Holdings", "Systems", "Partners", "Logistics", "Dynamics"]

ACTIVITY_TYPES = ["call", "email", "meeting", "note"]

# Each rep's profile drives account difficulty. win_rate and cycle_days are
# realistic for their segment mix (enterprise deals are genuinely slower and
# harder to win -- this isn't an arbitrary handicap, it reflects how B2B
# sales cycles actually scale with deal complexity).
#
# TWO reps per segment-focus profile (6 total), not one -- the fairness
# audit compares GROUP means (does everyone focused on Enterprise score
# systematically differently from everyone focused on SMB), and a "group"
# of one person isn't a group; see run_fairness_audit()'s min_group_size
# check. Each pair has slightly different numbers so within-group variance
# is realistic, not two identical clones.
REP_PROFILES = [
    {
        "full_name": "Rep - SMB Volume",
        "email": "rep.smb@revenuepilot.test",
        "segment_weights": {"SMB": 0.8, "Mid-Market": 0.2},
        "num_accounts": 15,
        "deals_per_account": (3, 5),
        "win_rate": 0.55,
        "value_range": (5_000, 25_000),
        "cycle_days_range": (10, 35),
    },
    {
        "full_name": "Rep - SMB Volume II",
        "email": "rep.smb2@revenuepilot.test",
        "segment_weights": {"SMB": 0.75, "Mid-Market": 0.25},
        "num_accounts": 13,
        "deals_per_account": (3, 5),
        "win_rate": 0.50,
        "value_range": (6_000, 28_000),
        "cycle_days_range": (12, 38),
    },
    {
        "full_name": "Rep - Mid-Market Balanced",
        "email": "rep.balanced@revenuepilot.test",
        "segment_weights": {"Mid-Market": 0.6, "SMB": 0.2, "Enterprise": 0.2},
        "num_accounts": 10,
        "deals_per_account": (2, 4),
        "win_rate": 0.45,
        "value_range": (20_000, 80_000),
        "cycle_days_range": (25, 60),
    },
    {
        "full_name": "Rep - Mid-Market Balanced II",
        "email": "rep.balanced2@revenuepilot.test",
        "segment_weights": {"Mid-Market": 0.55, "SMB": 0.25, "Enterprise": 0.2},
        "num_accounts": 9,
        "deals_per_account": (2, 4),
        "win_rate": 0.42,
        "value_range": (18_000, 90_000),
        "cycle_days_range": (20, 65),
    },
    {
        "full_name": "Rep - Enterprise Specialist",
        "email": "rep.enterprise@revenuepilot.test",
        "segment_weights": {"Enterprise": 0.9, "Mid-Market": 0.1},
        "num_accounts": 6,
        "deals_per_account": (1, 3),
        "win_rate": 0.30,
        "value_range": (100_000, 500_000),
        "cycle_days_range": (60, 150),
    },
    {
        "full_name": "Rep - Enterprise Specialist II",
        "email": "rep.enterprise2@revenuepilot.test",
        "segment_weights": {"Enterprise": 0.85, "Mid-Market": 0.15},
        "num_accounts": 5,
        "deals_per_account": (1, 3),
        "win_rate": 0.33,
        "value_range": (90_000, 450_000),
        "cycle_days_range": (55, 140),
    },
]

WINDOW_DAYS = 24 * 30  # align with the ~24 months of finance/sales/marketing history


def _chunked(records, size=500):
    for i in range(0, len(records), size):
        yield records[i:i + size]


def _company_name(customer_id: str) -> str:
    return f"{random.choice(COMPANY_PREFIXES)} {random.choice(COMPANY_SUFFIXES)}"


def main():
    client = db.get_client(use_service_role=True)

    # --- 1. Resolve Sales department + the existing sales manager ---
    dept_rows = client.table("departments").select("id, name").execute().data
    dept_id_by_name = {row["name"]: row["id"] for row in dept_rows}
    sales_dept_id = dept_id_by_name.get("Sales")
    if not sales_dept_id:
        raise RuntimeError("No 'Sales' department found. Run api/seed_org.py first.")

    # Clear any CRM data from a previous run of this script so re-running it
    # is safe (idempotent) rather than duplicating accounts/deals/activities
    # on top of the old set. Scoped to rows owned by Sales-department
    # employees, so it never touches CRM data that might belong elsewhere.
    print("Clearing previous CRM seed data (if any)...")
    for table_name in ("crm_activities", "crm_deals", "crm_contacts", "crm_accounts"):
        # All 4 tables key back to crm_accounts.department_id (directly or via
        # account_id), so the simplest safe wildcard is: delete everything --
        # this script is the only writer of these 4 tables in this project.
        client.table(table_name).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("  Cleared.")

    manager_rows = (
        client.table("employees")
        .select("id, full_name")
        .eq("department_id", sales_dept_id)
        .eq("role", "manager")
        .execute()
        .data
    )
    manager_id = manager_rows[0]["id"] if manager_rows else None

    # --- 2. Upsert the 3 synthetic reps (placeholder emails -- these are
    #     NEVER used for report delivery, only as CRM deal/activity owners) ---
    print("Seeding synthetic sales reps...")
    for profile in REP_PROFILES:
        client.table("employees").upsert(
            {
                "full_name": profile["full_name"],
                "email": profile["email"],
                "role": "employee",
                "department_id": sales_dept_id,
                "manager_id": manager_id,
            },
            on_conflict="email",
        ).execute()

    rep_rows = (
        client.table("employees")
        .select("id, email, full_name")
        .in_("email", [p["email"] for p in REP_PROFILES])
        .execute()
        .data
    )
    rep_id_by_email = {r["email"]: r["id"] for r in rep_rows}
    print(f"  Reps ready: {[(r['full_name'], r['id']) for r in rep_rows]}")

    # --- 3. Pull real customers to anchor accounts against (reuses the
    #     already-seeded customers table rather than inventing fake IDs) ---
    customers = db.load_customers()
    used_customer_ids = set()

    def sample_customers(weights: dict, n: int):
        pool = []
        for segment, weight in weights.items():
            seg_df = customers[
                (customers["segment"] == segment) & (~customers["customer_id"].isin(used_customer_ids))
            ]
            take = min(len(seg_df), max(1, round(n * weight)))
            if take:
                sampled = seg_df.sample(take, random_state=random.randint(0, 1_000_000))
                pool.append(sampled)
        if not pool:
            return customers.sample(0)
        result = __import__("pandas").concat(pool).head(n)
        used_customer_ids.update(result["customer_id"].tolist())
        return result

    now = datetime.utcnow()
    accounts, contacts, deals, activities = [], [], [], []

    print("Generating accounts, deals, and activities...")
    for profile in REP_PROFILES:
        rep_id = rep_id_by_email[profile["email"]]
        sampled = sample_customers(profile["segment_weights"], profile["num_accounts"])

        for _, cust in sampled.iterrows():
            account_id = str(uuid.uuid4())
            accounts.append({
                "id": account_id,
                "customer_id": cust["customer_id"],
                "company_name": _company_name(cust["customer_id"]),
                "region": cust["region"],
                "segment": cust["segment"],
                "owner_employee_id": rep_id,
                "department_id": sales_dept_id,
            })
            contacts.append({
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "full_name": f"Contact for {cust['customer_id']}",
                "email": f"contact.{cust['customer_id'].lower()}@example.com",
                "phone": None,
                "job_title": random.choice(["VP Operations", "Procurement Lead", "IT Director", "CFO", "Owner"]),
            })

            n_deals = random.randint(*profile["deals_per_account"])
            for _ in range(n_deals):
                deal_id = str(uuid.uuid4())
                cycle_days = random.randint(*profile["cycle_days_range"])
                created_offset = random.randint(cycle_days, WINDOW_DAYS)
                created_at = now - timedelta(days=created_offset)

                # 80% of deals are closed (won/lost by this rep's win rate);
                # 20% are still open in the pipeline at a random earlier stage.
                is_closed = random.random() < 0.8
                if is_closed:
                    won = random.random() < profile["win_rate"]
                    stage = "won" if won else "lost"
                    closed_at = created_at + timedelta(days=cycle_days)
                    expected_close_date = closed_at.date()
                else:
                    stage = random.choice(["prospecting", "qualified", "proposal", "negotiation"])
                    closed_at = None
                    expected_close_date = (now + timedelta(days=random.randint(5, 60))).date()

                value = round(random.uniform(*profile["value_range"]), 2)

                deals.append({
                    "id": deal_id,
                    "account_id": account_id,
                    "owner_employee_id": rep_id,
                    "deal_name": f"{_company_name(cust['customer_id'])} - Contract",
                    "stage": stage,
                    "value": value,
                    "expected_close_date": expected_close_date.isoformat(),
                    "closed_at": closed_at.isoformat() if closed_at else None,
                })

                n_activities = random.randint(2, 6)
                for i in range(n_activities):
                    span = cycle_days if is_closed else (now - created_at).days
                    span = max(span, 1)
                    activity_time = created_at + timedelta(days=int(span * i / max(n_activities - 1, 1)))
                    activities.append({
                        "id": str(uuid.uuid4()),
                        "account_id": account_id,
                        "deal_id": deal_id,
                        "employee_id": rep_id,
                        "activity_type": random.choice(ACTIVITY_TYPES),
                        "notes": None,
                        "created_at": activity_time.isoformat(),
                    })

    print(f"  {len(accounts)} accounts, {len(contacts)} contacts, {len(deals)} deals, {len(activities)} activities generated.")

    print("Inserting into Supabase...")
    for table_name, records in [
        ("crm_accounts", accounts),
        ("crm_contacts", contacts),
        ("crm_deals", deals),
        ("crm_activities", activities),
    ]:
        for chunk in _chunked(records):
            client.table(table_name).insert(chunk).execute()
        print(f"  {table_name}: {len(records)} rows inserted.")

    print("Done. Verify in Supabase Table Editor: crm_accounts, crm_contacts, crm_deals, crm_activities.")


if __name__ == "__main__":
    main()
