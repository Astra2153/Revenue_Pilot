"""
Adversarial test battery for nlquery.validate_sql().

Each case represents SQL an LLM might plausibly emit -- either from a normal
question, or from a user actively trying to make it emit something dangerous.
"""

import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("RESEND_API_KEY", "dummy")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "dummy")
sys.path.insert(0, "/home/claude/api")

import nlquery
from nlquery import validate_sql, UnsafeQueryError, enforce_row_limit

# (label, sql, division, should_pass)
CASES = [
    # ---- legitimate queries that MUST pass ----
    ("plain aggregate",
     "select region, sum(revenue) as total from sales_transactions group by region order by total desc",
     "sales", True),
    ("join across allowed tables",
     "select c.segment, sum(s.revenue) as rev from sales_transactions s join customers c on s.customer_id = c.customer_id group by c.segment",
     "sales", True),
    ("CTE",
     "with monthly as (select month, revenue from finance_records) select month, revenue from monthly order by month",
     "finance", True),
    ("literal containing a scary word (must NOT false-positive)",
     "select company_name from crm_accounts where company_name = 'Drop Systems Ltd'",
     "sales", True),
    ("markdown fence gets stripped",
     "```sql\nselect channel, spend from marketing_campaigns\n```",
     "marketing", True),
    ("trailing semicolon allowed",
     "select month, revenue from finance_records;",
     "finance", True),

    # ---- destructive / injection attempts that MUST be rejected ----
    ("bare DROP", "drop table customers", "admin", False),
    ("stacked statement", "select 1 from customers; drop table customers", "admin", False),
    ("line comment hiding payload",
     "select customer_id from customers -- ; drop table customers", "admin", False),
    ("block comment", "select /* sneaky */ customer_id from customers", "admin", False),
    ("data-modifying CTE",
     "with x as (delete from customers returning *) select * from x", "admin", False),
    ("UPDATE disguised as read",
     "update customers set segment = 'SMB'", "admin", False),
    ("INSERT", "insert into customers values ('x','y','z','2020-01-01')", "admin", False),
    ("TRUNCATE", "truncate customers", "admin", False),
    ("GRANT", "grant all on customers to anon", "admin", False),
    ("pg_sleep DoS", "select pg_sleep(60) from customers", "admin", False),
    ("file read", "select pg_read_file('/etc/passwd') from customers", "admin", False),
    ("system catalog", "select * from pg_catalog.pg_tables", "admin", False),
    ("information_schema", "select table_name from information_schema.tables", "admin", False),
    ("auth schema", "select * from auth.users", "admin", False),
    ("SELECT INTO write", "select * into evil from customers", "admin", False),
    ("empty query", "", "admin", False),
    ("non-select expression only", "select 1", "admin", False),

    # ---- cross-division access that MUST be rejected ----
    ("marketing reaching into finance",
     "select month, revenue from finance_records", "marketing", False),
    ("sales reaching into employees (PII)",
     "select full_name, email from employees", "sales", False),
    ("customer division reaching into audit_log",
     "select * from audit_log", "customer", False),
    ("finance reaching into crm_deals",
     "select deal_name, value from crm_deals", "finance", False),
    ("hidden cross-division reference in subquery",
     "select customer_id from customers where customer_id in (select customer_id from crm_accounts)",
     "marketing", False),
    ("unknown table", "select * from secret_table", "admin", False),
    ("unknown division", "select * from customers", "not_a_division", False),
]


def main():
    passed = failed = 0
    for label, sql, division, should_pass in CASES:
        try:
            validate_sql(sql, division)
            actual = True
            detail = "accepted"
        except UnsafeQueryError as e:
            actual = False
            detail = str(e)
        except Exception as e:  # any other exception is itself a bug
            actual = None
            detail = f"UNEXPECTED {type(e).__name__}: {e}"

        ok = actual is should_pass
        mark = "PASS" if ok else "**FAIL**"
        if ok:
            passed += 1
        else:
            failed += 1
        expect = "allow" if should_pass else "block"
        print(f"[{mark}] ({expect:5s}) {label:52s} -> {detail[:70]}")

    print()
    print(f"{passed} passed, {failed} failed, {len(CASES)} total")

    print()
    print("Row-limit wrapping:")
    print(" ", enforce_row_limit("select region from sales_transactions"))

    print()
    print("Division allowlists:")
    for div, tables in nlquery.ALLOWED_TABLES.items():
        print(f"  {div:10s} -> {sorted(tables)}")

    return failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
