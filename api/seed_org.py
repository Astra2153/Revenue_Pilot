"""
seed_org.py

Seeds the organizational structure (departments + employees) used for
role-based access and department-scoped monthly reports. Separate from
seed_data.py (which seeds the synthetic BUSINESS data) since this is
organizational/test data you'll likely want to edit by hand.

IMPORTANT: Resend's free tier (no verified domain) can only send email TO
your own verified address, not to arbitrary addresses. All 4 addresses
below are real Gmail/institute addresses the user owns, so this is fine
for testing the ADMIN report (their own account's verified address). The
department-scoped reports will still only actually be delivered to
whichever one address is verified in Resend -- the others will get a
"success" response from Resend's API without a message landing, until a
sending domain is verified.

Run once from the project root:
    python api/seed_org.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

DEPARTMENTS = ["Sales", "Marketing", "Finance", "Customer Intelligence"]

# auth_user_id is left blank since no real login/signup flow exists yet
# (that comes in the frontend phase); these are just recipient + role
# records for now.
EMPLOYEES = [
    {"full_name": "Ashmit Katale (Admin)", "email": "ashmit.katale@gmail.com", "department": None, "role": "admin"},
    {"full_name": "Sanjay Katale", "email": "sanjay.katale@gmail.com", "department": "Sales", "role": "manager"},
    {"full_name": "Ashmit K (Marketing)", "email": "ashmit.kth@gmail.com", "department": "Marketing", "role": "manager"},
    {"full_name": "Ashmit Katale (Finance)", "email": "ashmit.katale.btech2023@sitpune.edu.in", "department": "Finance", "role": "manager"},
]


def main():
    client = db.get_client(use_service_role=True)

    print("Seeding departments...")
    dept_records = [{"name": name} for name in DEPARTMENTS]
    client.table("departments").upsert(dept_records, on_conflict="name").execute()

    dept_rows = client.table("departments").select("id, name").execute().data
    dept_id_by_name = {row["name"]: row["id"] for row in dept_rows}
    print(f"  Departments ready: {dept_id_by_name}")

    print("Seeding employees...")
    for emp in EMPLOYEES:
        record = {
            "full_name": emp["full_name"],
            "email": emp["email"],
            "role": emp["role"],
            "department_id": dept_id_by_name.get(emp["department"]) if emp["department"] else None,
        }
        client.table("employees").upsert(record, on_conflict="email").execute()

    print("Done. Verify rows in Supabase Table Editor: departments, employees.")


if __name__ == "__main__":
    main()
