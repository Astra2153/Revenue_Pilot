"""
api.py

FastAPI service that wraps the existing analytics.py engine
(RevenueForecaster, CustomerSegmenter, ChurnScorer, compute_marketing_roi,
generate_insights) and serves it over HTTP, reading live data from
Supabase via db.py instead of an in-memory DataFrame.

Run locally:
    uvicorn api.api:app --reload --port 8000

Then visit http://localhost:8000/docs for interactive API docs.
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root (for analytics.py, data_generator.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # api/ folder itself (for db.py)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

import db
import chatbot
import report
import nlquery
import kpi
from analytics import (
    RevenueForecaster,
    CustomerSegmenter,
    ChurnScorer,
    AnomalyDetector,
    CohortAnalyzer,
    compute_marketing_roi,
    generate_insights,
)

app = FastAPI(title="RevenuePilot API", version="0.1.0")

# Allow the React frontend (localhost during dev, Vercel domain in prod) to call this API.
# Tighten allow_origins to your actual frontend URL(s) before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Simple in-process cache: reload data + refit models at most once per
# CACHE_TTL_SECONDS, instead of hitting Supabase and refitting sklearn
# models on every single request.
# ------------------------------------------------------------------
CACHE_TTL_SECONDS = 300
_cache = {"loaded_at": None, "data": None}


def get_data():
    now = datetime.utcnow()
    if _cache["loaded_at"] and (now - _cache["loaded_at"]).total_seconds() < CACHE_TTL_SECONDS:
        return _cache["data"]

    customers = db.load_customers()
    sales = db.load_sales()
    marketing = db.load_marketing()
    finance = db.load_finance()

    if sales.empty or finance.empty:
        raise HTTPException(status_code=503, detail="No data found -- has seed_data.py been run yet?")

    forecaster = RevenueForecaster()
    forecaster.fit(finance)

    segmenter = CustomerSegmenter(n_clusters=4)
    rfm_result = segmenter.fit_predict(sales, customers)

    churn_scorer = ChurnScorer()
    churn_result = churn_scorer.fit_predict(rfm_result)

    avg_customer_value = rfm_result["monetary"].median()
    roi_summary = compute_marketing_roi(marketing, avg_customer_value)

    anomaly_detector = AnomalyDetector(contamination=0.08)
    finance_anomalies = anomaly_detector.detect_finance(finance)
    marketing_anomalies = anomaly_detector.detect_marketing(marketing)
    sales_anomalies = anomaly_detector.detect_sales(sales, customers, top_n=100)

    cohort_analyzer = CohortAnalyzer()
    cohort_table = cohort_analyzer.build_cohort_table(sales, customers)
    cohort_matrix = cohort_analyzer.retention_matrix(cohort_table)

    bundle = {
        "customers": customers,
        "sales": sales,
        "marketing": marketing,
        "finance": finance,
        "forecaster": forecaster,
        "segmenter": segmenter,
        "rfm_result": rfm_result,
        "churn_scorer": churn_scorer,
        "churn_result": churn_result,
        "roi_summary": roi_summary,
        "finance_anomalies": finance_anomalies,
        "marketing_anomalies": marketing_anomalies,
        "sales_anomalies": sales_anomalies,
        "cohort_table": cohort_table,
        "cohort_matrix": cohort_matrix,
    }
    _cache["data"] = bundle
    _cache["loaded_at"] = now
    return bundle


def df_to_records(df: pd.DataFrame) -> list:
    """
    JSON-safe conversion: datetimes -> ISO strings, NaN/NaT -> null.

    Round-trips through pandas' own to_json() rather than plain
    to_dict("records") -- pandas sometimes stores a missing value as a float
    NaN even in an object-dtype (string) column (e.g. an admin employee's
    department_id, which is genuinely absent, not a string). Python's
    json.dumps refuses to encode NaN at all (ValueError: "Out of range float
    values are not JSON compliant"), which crashed /api/employees in
    testing. pandas.to_json() correctly emits NaN as JSON null, so this
    guards every endpoint that uses this helper, not just employees.
    """
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return json.loads(out.to_json(orient="records"))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/refresh")
def refresh_cache():
    """Forces an immediate reload from Supabase + model refit, bypassing the cache TTL."""
    _cache["loaded_at"] = None
    get_data()
    return {"status": "refreshed"}


@app.get("/api/forecast")
def forecast(periods: int = Query(6, ge=1, le=24)):
    data = get_data()
    fc = data["forecaster"].forecast(periods=periods)
    return {
        "metrics": data["forecaster"].metrics_,
        "forecast": df_to_records(fc),
        "feature_importances": df_to_records(data["forecaster"].feature_importances()),
    }


@app.get("/api/segments")
def segments():
    data = get_data()
    return {"customers": df_to_records(data["rfm_result"])}


@app.get("/api/segments/summary")
def segments_summary():
    data = get_data()
    summary = data["segmenter"].segment_summary(data["rfm_result"])
    return {"summary": df_to_records(summary)}


@app.get("/api/churn")
def churn():
    data = get_data()
    return {
        "metrics": data["churn_scorer"].metrics_,
        "customers": df_to_records(data["churn_result"]),
        "feature_importances": df_to_records(data["churn_scorer"].feature_importances()),
    }


@app.get("/api/marketing/roi")
def marketing_roi():
    data = get_data()
    return {"channels": df_to_records(data["roi_summary"])}


@app.get("/api/insights")
def insights():
    data = get_data()
    fc = data["forecaster"].forecast(periods=6)
    result = generate_insights(
        data["sales"], data["marketing"], data["finance"],
        data["rfm_result"], data["churn_result"], data["roi_summary"], fc,
    )
    return result


@app.get("/api/sales/raw")
def sales_raw(limit: int = Query(500, ge=1, le=5000)):
    data = get_data()
    return {"rows": df_to_records(data["sales"].head(limit))}


@app.get("/api/finance/raw")
def finance_raw():
    data = get_data()
    return {"rows": df_to_records(data["finance"])}


@app.get("/api/marketing/raw")
def marketing_raw():
    data = get_data()
    return {"rows": df_to_records(data["marketing"])}


@app.get("/api/anomalies/finance")
def anomalies_finance():
    data = get_data()
    df = data["finance_anomalies"]
    return {
        "rows": df_to_records(df),
        "flagged_count": int(df["is_anomaly"].sum()),
    }


@app.get("/api/anomalies/marketing")
def anomalies_marketing():
    data = get_data()
    df = data["marketing_anomalies"]
    return {
        "rows": df_to_records(df),
        "flagged_count": int(df["is_anomaly"].sum()),
    }


@app.get("/api/anomalies/sales")
def anomalies_sales():
    data = get_data()
    df = data["sales_anomalies"]
    return {
        "rows": df_to_records(df),
        "flagged_count": int(df["is_anomaly"].sum()),
    }


@app.get("/api/cohorts")
def cohorts():
    """Long-format cohort table: one row per (cohort_month, period_number)."""
    data = get_data()
    return {"rows": df_to_records(data["cohort_table"])}


@app.get("/api/cohorts/matrix")
def cohorts_matrix():
    """
    Wide cohort x period retention matrix, shaped for a heatmap chart.
    Each row is one signup cohort; each key under 'periods' is the number
    of months since that cohort signed up, mapped to its retention rate
    (0.0-1.0, or null where that cohort hasn't reached that period yet).
    """
    data = get_data()
    matrix = data["cohort_matrix"].reset_index()
    matrix["cohort_month"] = pd.to_datetime(matrix["cohort_month"]).dt.strftime("%Y-%m")
    period_cols = [c for c in matrix.columns if c != "cohort_month"]

    rows = []
    for _, row in matrix.iterrows():
        periods = {}
        for col in period_cols:
            val = row[col]
            periods[str(col)] = None if pd.isna(val) else float(val)
        rows.append({"cohort_month": row["cohort_month"], "periods": periods})

    return {"rows": rows}


class ChatRequest(BaseModel):
    message: str
    module: str | None = None  # "sales" | "marketing" | "finance" | "customer" | None (all)


@app.post("/api/chat")
def chat(req: ChatRequest):
    if req.module and req.module not in chatbot.MODULES:
        raise HTTPException(status_code=422, detail=f"module must be one of {sorted(chatbot.MODULES)} or omitted")
    data = get_data()
    result = chatbot.ask(req.message, data, module=req.module)
    return result


@app.get("/api/reports/monthly/preview")
def report_preview():
    """Builds the report data + both narratives WITHOUT sending an email -- use this to check content first."""
    data = get_data()
    report_data = report.gather_monthly_report_data(data)
    narrative = report.generate_report_narrative(report_data)
    causal_narrative = report.generate_causal_narrative(data, report_data)
    html = report.render_report_html(report_data, narrative, causal_narrative)
    return {"report_data": report_data, "narrative": narrative, "causal_narrative": causal_narrative, "html": html}


class SendReportRequest(BaseModel):
    to_emails: list[str]


@app.post("/api/reports/monthly/send")
def report_send(req: SendReportRequest):
    if not req.to_emails:
        raise HTTPException(status_code=422, detail="to_emails must contain at least one address")
    data = get_data()
    result = report.build_and_send_monthly_report(data, req.to_emails)
    return {
        "narrative": result["narrative"],
        "send_result": result["send_result"],
    }


class NLQueryRequest(BaseModel):
    question: str
    division: str = "admin"  # "sales" | "marketing" | "finance" | "customer" | "admin"
    explain: bool = True


@app.post("/api/query")
def natural_language_query(req: NLQueryRequest):
    """
    Ask a question in plain English; get back the generated SQL, the rows, and a
    one-line summary.

    The `division` controls which tables the query may touch (see
    nlquery.ALLOWED_TABLES). Generated SQL is validated before execution and run
    read-only -- a query that fails validation returns status 'refused' with the
    reason, and is never executed.
    """
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    if req.division not in nlquery.ALLOWED_TABLES:
        raise HTTPException(
            status_code=422,
            detail=f"division must be one of {sorted(nlquery.ALLOWED_TABLES)}",
        )
    return nlquery.ask_data(req.question, division=req.division, explain=req.explain)


@app.get("/api/query/schema")
def query_schema(division: str = Query("admin")):
    """Which tables and columns a given division can query. Useful for the UI's help text."""
    if division not in nlquery.ALLOWED_TABLES:
        raise HTTPException(
            status_code=422,
            detail=f"division must be one of {sorted(nlquery.ALLOWED_TABLES)}",
        )
    allowed = sorted(nlquery.ALLOWED_TABLES[division])
    return {
        "division": division,
        "tables": {t: nlquery.TABLE_SCHEMAS[t] for t in allowed if t in nlquery.TABLE_SCHEMAS},
        "max_rows": nlquery.MAX_ROWS,
    }


@app.get("/api/kpi/company")
def kpi_company():
    """CEO scorecard: the monthly report's finance/sales/marketing/customer blocks plus company-wide CRM stats."""
    data = get_data()
    return kpi.gather_company_kpis(data)


@app.get("/api/kpi/leaderboard")
def kpi_leaderboard():
    """
    Every sales employee's RAW and difficulty-adjusted NORMALIZED metrics,
    side by side, sorted by the normalized figure. Also returns the
    data-driven difficulty weights themselves, so the adjustment is always
    visible and auditable rather than a hidden black box.
    """
    return kpi.build_leaderboard()


@app.get("/api/kpi/employee/{employee_id}")
def kpi_employee(employee_id: str):
    """One employee's raw + normalized metrics plus a strictly evidence-grounded narrative."""
    result = kpi.get_employee_kpi(employee_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/kpi/fairness-audit")
def kpi_fairness_audit():
    """
    Deterministic statistical check: does the NORMALIZED score still show a
    systematic gap across segment-focus groups after difficulty-weighting?
    Not an LLM judgment call -- a factual computation over the same data
    the leaderboard uses.
    """
    return kpi.run_fairness_audit()


# ------------------------------------------------------------------
# Employee & department management (Admin Portal, step 11)
#
# NOTE ON ACCESS CONTROL: like /api/query's division parameter, these
# endpoints are currently open to any caller -- there is no authenticated
# "is this person actually an admin" check yet. That belongs in the auth
# step alongside the frontend login work. Flagging it here rather than
# silently shipping write endpoints that look protected but aren't.
# ------------------------------------------------------------------
class EmployeeCreateRequest(BaseModel):
    full_name: str
    email: str
    role: str  # "admin" | "manager" | "employee"
    department_id: str | None = None
    manager_id: str | None = None


class EmployeeUpdateRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    role: str | None = None
    department_id: str | None = None
    manager_id: str | None = None


@app.get("/api/departments")
def list_departments():
    return db.get_departments()


@app.get("/api/employees")
def list_employees():
    df = db.get_all_employees()
    if df.empty:
        return []
    return df_to_records(df)


@app.post("/api/employees")
def create_employee(req: EmployeeCreateRequest):
    result = db.create_employee(
        full_name=req.full_name,
        email=req.email,
        role=req.role,
        department_id=req.department_id,
        manager_id=req.manager_id,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Employee could not be created.")
    db.create_audit_log_entry(table_name="employees", record_id=result["id"], action="insert", new_data=result)
    return result


@app.put("/api/employees/{employee_id}")
def update_employee(employee_id: str, req: EmployeeUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update.")
    old_data = db.get_employee_by_id(employee_id)
    result = db.update_employee(employee_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail=f"No employee found with id {employee_id}")
    db.create_audit_log_entry(
        table_name="employees", record_id=employee_id, action="update",
        old_data=old_data or None, new_data=result,
    )
    return result


@app.delete("/api/employees/{employee_id}")
def delete_employee(employee_id: str):
    old_data = db.get_employee_by_id(employee_id)
    deleted = db.delete_employee(employee_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No employee found with id {employee_id}")
    db.create_audit_log_entry(
        table_name="employees", record_id=employee_id, action="delete", old_data=old_data or None,
    )
    return {"deleted": True, "employee_id": employee_id}


@app.get("/api/audit-log")
def audit_log(table_name: str = Query(None), limit: int = Query(200)):
    df = db.get_audit_log(table_name=table_name, limit=limit)
    if df.empty:
        return []
    return df_to_records(df)


@app.post("/api/reports/monthly/send-all")
def report_send_all():
    """
    Sends the full combined monthly report to every admin employee --
    recipients pulled live from Supabase (employees table where
    role='admin'), not typed by hand. Run api/seed_org.py first if no
    admin employees have been seeded yet.
    """
    data = get_data()
    result = report.send_all_reports(data)
    return result
