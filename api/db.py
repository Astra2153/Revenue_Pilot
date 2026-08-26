"""
db.py

Supabase data-access layer. Reads from the tables created in
revenuepilot_schema.sql and returns pandas DataFrames shaped exactly
like the ones data_generator.py used to produce in-memory -- so
analytics.py (RevenueForecaster, CustomerSegmenter, ChurnScorer,
compute_marketing_roi, generate_insights) needs ZERO changes.

Also handles writing data (used by seed_data.py to load the synthetic
dataset into Supabase once).

Requires a .env file at the project root with:
    SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
    SUPABASE_ANON_KEY=...
    SUPABASE_SERVICE_ROLE_KEY=...   (only needed for seeding/writes)
"""

import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_ANON_KEY. Check your .env file at the project root."
    )


def get_client(use_service_role: bool = False) -> Client:
    """
    Returns a Supabase client. Use the anon key for normal reads (the API
    server acts as an authenticated/service context in practice, but for
    local dev the anon key + permissive read policies are enough).
    Use the service_role key only for the one-off seed script, since RLS
    would otherwise block bulk inserts from an unauthenticated context.
    """
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
    if use_service_role and not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY not set -- required for seeding data.")
    return create_client(SUPABASE_URL, key)


PAGE_SIZE = 1000  # Supabase default row cap per request; loaders page through this


def _fetch_all(client: Client, table: str, order_col: str = None) -> list:
    """Pages through a table so datasets larger than one page still load fully."""
    rows = []
    start = 0
    while True:
        q = client.table(table).select("*").range(start, start + PAGE_SIZE - 1)
        if order_col:
            q = q.order(order_col)
        res = q.execute()
        batch = res.data
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


# ------------------------------------------------------------------
# Readers -- return DataFrames shaped like data_generator.py's output
#
# NOTE: these use the service_role key, not the anon key. RLS exists to
# protect DIRECT browser/client access to Supabase; this API server is a
# trusted backend process, so it reads with elevated access and enforces
# its own authorization (role/department checks) in the API layer itself
# in later steps -- rather than relying on RLS's auth.role()='authenticated'
# check, which only applies to a logged-in end-user's own Supabase session,
# not to server-to-server calls like this one.
# ------------------------------------------------------------------
def load_customers() -> pd.DataFrame:
    client = get_client(use_service_role=True)
    rows = _fetch_all(client, "customers")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["signup_date"] = pd.to_datetime(df["signup_date"])
    return df[["customer_id", "segment", "region", "signup_date"]]


def load_sales() -> pd.DataFrame:
    client = get_client(use_service_role=True)
    rows = _fetch_all(client, "sales_transactions")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = df["revenue"].astype(float)
    df["units_sold"] = df["units_sold"].astype(int)
    return df[[
        "transaction_id", "customer_id", "region", "date",
        "product_category", "sales_channel", "revenue", "units_sold",
    ]].assign(segment=None)  # segment gets merged back in via customers if needed downstream


def load_marketing() -> pd.DataFrame:
    client = get_client(use_service_role=True)
    rows = _fetch_all(client, "marketing_campaigns")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["month"])
    for col in ["spend", "impressions", "clicks", "leads_generated", "conversions"]:
        df[col] = df[col].astype(float if col == "spend" else int)
    return df[["month", "channel", "spend", "impressions", "clicks", "leads_generated", "conversions"]]


def load_finance() -> pd.DataFrame:
    client = get_client(use_service_role=True)
    rows = _fetch_all(client, "finance_records")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["month"])
    numeric_cols = [
        "revenue", "marketing_spend", "cogs", "gross_profit",
        "other_opex", "operating_profit", "cash_flow",
    ]
    for col in numeric_cols:
        df[col] = df[col].astype(float)
    return df.sort_values("month").reset_index(drop=True)


# ------------------------------------------------------------------
# Writers -- used only by seed_data.py (requires service_role key)
# ------------------------------------------------------------------
def _chunked(records: list, size: int = 500):
    for i in range(0, len(records), size):
        yield records[i:i + size]


def insert_customers(df: pd.DataFrame):
    client = get_client(use_service_role=True)
    records = df.assign(signup_date=df["signup_date"].dt.strftime("%Y-%m-%d")).to_dict("records")
    for chunk in _chunked(records):
        client.table("customers").insert(chunk).execute()


def insert_sales(df: pd.DataFrame):
    client = get_client(use_service_role=True)
    keep_cols = ["transaction_id", "customer_id", "region", "date", "product_category", "sales_channel", "revenue", "units_sold"]
    records = df[keep_cols].assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_dict("records")
    for chunk in _chunked(records):
        client.table("sales_transactions").insert(chunk).execute()


def insert_marketing(df: pd.DataFrame):
    client = get_client(use_service_role=True)
    records = df.assign(month=df["month"].dt.strftime("%Y-%m-%d")).to_dict("records")
    for chunk in _chunked(records):
        client.table("marketing_campaigns").insert(chunk).execute()


def insert_finance(df: pd.DataFrame):
    client = get_client(use_service_role=True)
    records = df.assign(month=df["month"].dt.strftime("%Y-%m-%d")).to_dict("records")
    for chunk in _chunked(records):
        client.table("finance_records").insert(chunk).execute()


# ------------------------------------------------------------------
# Org readers -- used by report.py for department-scoped report recipients
# ------------------------------------------------------------------
def get_employees_by_department(department_name: str) -> list:
    """Returns [{full_name, email, role}, ...] for everyone in one department."""
    client = get_client(use_service_role=True)
    dept = client.table("departments").select("id").eq("name", department_name).execute().data
    if not dept:
        return []
    dept_id = dept[0]["id"]
    rows = client.table("employees").select("full_name, email, role").eq("department_id", dept_id).execute().data
    return rows


def get_admin_emails() -> list:
    """Returns [{full_name, email}, ...] for everyone with the admin role."""
    client = get_client(use_service_role=True)
    rows = client.table("employees").select("full_name, email").eq("role", "admin").execute().data
    return rows


# ------------------------------------------------------------------
# CRM readers -- used by kpi.py for company-wide and per-employee performance
# ------------------------------------------------------------------
def get_all_employees() -> pd.DataFrame:
    """All employees with their department name, for the KPI leaderboard."""
    client = get_client(use_service_role=True)
    rows = client.table("employees").select("id, full_name, email, role, department_id, manager_id").execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    dept_rows = client.table("departments").select("id, name").execute().data
    dept_name_by_id = {d["id"]: d["name"] for d in dept_rows}
    df["department"] = df["department_id"].map(dept_name_by_id)
    return df


def get_crm_deals(owner_employee_id: str = None) -> pd.DataFrame:
    """All CRM deals, optionally filtered to one owner. Joined with account segment."""
    client = get_client(use_service_role=True)
    query = client.table("crm_deals").select("*, crm_accounts(segment, region, company_name)")
    if owner_employee_id:
        query = query.eq("owner_employee_id", owner_employee_id)
    rows = query.execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Flatten the joined account fields out of the nested dict Supabase returns.
    account_info = df.pop("crm_accounts").apply(pd.Series)
    df["segment"] = account_info.get("segment")
    df["region"] = account_info.get("region")
    df["company_name"] = account_info.get("company_name")
    return df


def get_crm_activities(employee_id: str = None) -> pd.DataFrame:
    """All CRM activities, optionally filtered to one employee."""
    client = get_client(use_service_role=True)
    query = client.table("crm_activities").select("*")
    if employee_id:
        query = query.eq("employee_id", employee_id)
    rows = query.execute().data
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Employee & department management -- used by the Admin Portal (step 11)
# to add/edit/remove employees and view departments. Writes use the
# service_role client (bypasses RLS by design; RBAC is enforced at the
# API layer, same as the rest of this project).
# ------------------------------------------------------------------
def get_departments() -> list:
    """Returns [{id, name}, ...] for every department."""
    client = get_client(use_service_role=True)
    return client.table("departments").select("id, name").execute().data


def create_employee(full_name: str, email: str, role: str, department_id: str = None, manager_id: str = None) -> dict:
    """Inserts a new employee row and returns it (including its generated id)."""
    client = get_client(use_service_role=True)
    row = {
        "full_name": full_name,
        "email": email,
        "role": role,
        "department_id": department_id,
        "manager_id": manager_id,
    }
    result = client.table("employees").insert(row).execute()
    return result.data[0] if result.data else {}


def update_employee(employee_id: str, updates: dict) -> dict:
    """
    Updates only the fields present in `updates` (a partial update -- fields
    not included are left untouched). Returns the updated row, or {} if no
    employee with that id was found.
    """
    client = get_client(use_service_role=True)
    result = client.table("employees").update(updates).eq("id", employee_id).execute()
    return result.data[0] if result.data else {}


def delete_employee(employee_id: str) -> bool:
    """Deletes an employee by id. Returns True if a row was actually deleted."""
    client = get_client(use_service_role=True)
    result = client.table("employees").delete().eq("id", employee_id).execute()
    return len(result.data) > 0


# ------------------------------------------------------------------
# Audit log (step 15) -- reads/writes audit_log, the table already defined
# in revenuepilot_schema.sql. A Postgres trigger auto-logs crm_deals
# changes; employee changes (create/update/delete via the Admin Portal)
# are logged explicitly from api.py below, since there's no equivalent
# trigger on the employees table and no authenticated "who did this" yet
# -- employee_id on these entries is left null until a real auth layer
# exists to attribute the action to an actual logged-in user.
# ------------------------------------------------------------------
def get_employee_by_id(employee_id: str) -> dict:
    """Returns a single employee row (or {} if not found) -- used to capture
    the 'before' state for audit logging on update/delete."""
    client = get_client(use_service_role=True)
    result = client.table("employees").select("*").eq("id", employee_id).execute()
    return result.data[0] if result.data else {}


def create_audit_log_entry(table_name: str, record_id: str, action: str, old_data: dict = None, new_data: dict = None, employee_id: str = None) -> dict:
    """Inserts one audit_log row. action is 'insert' | 'update' | 'delete'."""
    client = get_client(use_service_role=True)
    row = {
        "employee_id": employee_id,
        "table_name": table_name,
        "record_id": record_id,
        "action": action,
        "old_data": old_data,
        "new_data": new_data,
    }
    result = client.table("audit_log").insert(row).execute()
    return result.data[0] if result.data else {}


def get_audit_log(table_name: str = None, limit: int = 200) -> pd.DataFrame:
    """
    Most recent audit_log rows, newest first, optionally filtered to one
    table_name (e.g. 'employees' or 'crm_deals'). Joined with the acting
    employee's name where known (many rows will have employee_id=null --
    see module note above).
    """
    client = get_client(use_service_role=True)
    query = client.table("audit_log").select("*").order("created_at", desc=True).limit(limit)
    if table_name:
        query = query.eq("table_name", table_name)
    rows = query.execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    all_employees = get_all_employees()
    if not all_employees.empty:
        name_by_id = dict(zip(all_employees["id"], all_employees["full_name"]))
        df["employee_name"] = df["employee_id"].map(name_by_id)
    else:
        df["employee_name"] = None
    return df
