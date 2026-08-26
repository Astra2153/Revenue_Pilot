"""
report.py

Monthly AI-written report for RevenuePilot: gathers month-over-month
comparisons across sales/marketing/finance/customer intelligence, has
Gemini write a plain-English narrative summary, renders it as an HTML
email, and sends it via Resend.

NOTE on the narrative step: this first version writes a solid, accurate
SUMMARY of what changed each module. The next-level version -- tracing
WHY things moved across modules (e.g. a marketing spend cut showing up
as a lead dip two months later, then a revenue dip now) -- is a genuinely
harder, multi-step reasoning problem, and is the one piece of this whole
build worth switching to Opus for, as a follow-up deepening pass on
build_causal_prompt() below. Everything else here is fine on Sonnet.

Requires RESEND_API_KEY in .env (in addition to GEMINI_API_KEY, already
required by chatbot.py).
"""

import os
import pandas as pd
from dotenv import load_dotenv
from google.genai import types

import resend
import chatbot  # reuses the same Gemini client + PRIMARY/FALLBACK model constants
import db  # for department/admin employee lookups in send_all_reports()

load_dotenv()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
if not RESEND_API_KEY:
    raise RuntimeError("Missing RESEND_API_KEY. Add it to your .env file (from resend.com).")
resend.api_key = RESEND_API_KEY

# Resend's shared test domain -- works out of the box for sending to your
# OWN verified email while testing. Swap this for a verified custom domain
# (e.g. reports@yourdomain.com) once you set one up in Resend, to send to
# real recipients beyond your own inbox.
DEFAULT_FROM_ADDRESS = "RevenuePilot Reports <onboarding@resend.dev>"


# ------------------------------------------------------------------
# 1. Gather month-over-month comparisons across all four modules
# ------------------------------------------------------------------
def gather_monthly_report_data(bundle: dict) -> dict:
    """
    Builds a structured dict of this month vs. last month across finance,
    sales, marketing, and customer intelligence -- the raw material the
    narrative gets written from. Pure pandas comparisons, no LLM calls.
    """
    finance = bundle["finance"].sort_values("month").reset_index(drop=True)
    latest_fin = finance.iloc[-1]
    prev_fin = finance.iloc[-2] if len(finance) >= 2 else None

    def pct_change(curr, prev):
        if prev in (None, 0) or prev != prev:  # None or NaN
            return None
        return round((curr - prev) / prev * 100, 1)

    finance_block = {
        "period": latest_fin["month"].strftime("%B %Y"),
        "revenue": float(latest_fin["revenue"]),
        "revenue_mom_pct": pct_change(latest_fin["revenue"], prev_fin["revenue"] if prev_fin is not None else None),
        "gross_margin_pct": round(latest_fin["gross_profit"] / latest_fin["revenue"] * 100, 1) if latest_fin["revenue"] else None,
        "operating_profit": float(latest_fin["operating_profit"]),
        "cash_flow": float(latest_fin["cash_flow"]),
    }

    sales = bundle["sales"].copy()
    sales["month"] = pd.to_datetime(sales["date"]).values.astype("datetime64[M]")
    latest_month = sales["month"].max()
    prev_month = (pd.Timestamp(latest_month) - pd.DateOffset(months=1)).to_period("M").to_timestamp()
    rev_by_region_latest = sales[sales["month"] == latest_month].groupby("region")["revenue"].sum()
    top_region = rev_by_region_latest.idxmax() if not rev_by_region_latest.empty else None

    sales_block = {
        "top_region_this_month": top_region,
        "transactions_this_month": int((sales["month"] == latest_month).sum()),
        "anomalies_flagged": int(bundle["sales_anomalies"]["is_anomaly"].sum()),
    }

    marketing = bundle["marketing"].copy()
    latest_mkt_month = marketing["month"].max()
    mkt_latest = marketing[marketing["month"] == latest_mkt_month]
    roi = bundle["roi_summary"].sort_values("roi_multiple", ascending=False)

    marketing_block = {
        "period_spend": float(mkt_latest["spend"].sum()),
        "period_conversions": int(mkt_latest["conversions"].sum()),
        "best_channel": roi.iloc[0]["channel"] if not roi.empty else None,
        "best_channel_roi": round(float(roi.iloc[0]["roi_multiple"]), 2) if not roi.empty else None,
        "weakest_channel": roi.iloc[-1]["channel"] if not roi.empty else None,
        "weakest_channel_roi": round(float(roi.iloc[-1]["roi_multiple"]), 2) if not roi.empty else None,
        "anomalies_flagged": int(bundle["marketing_anomalies"]["is_anomaly"].sum()),
    }

    rfm = bundle["rfm_result"]
    churn = bundle["churn_result"]
    customer_block = {
        "total_customers": int(len(rfm)),
        "high_risk_churn_pct": round((churn["churn_risk"] == "High Risk").mean() * 100, 1),
        "top_segment": rfm["segment_label"].value_counts().idxmax() if "segment_label" in rfm.columns else None,
    }

    finance_anomaly_count = int(bundle["finance_anomalies"]["is_anomaly"].sum())

    return {
        "finance": finance_block,
        "sales": sales_block,
        "marketing": marketing_block,
        "customer": customer_block,
        "finance_anomalies_total": finance_anomaly_count,
    }


# ------------------------------------------------------------------
# 2. Narrative generation (Gemini) -- see module docstring re: Opus
# ------------------------------------------------------------------
def _build_narrative_prompt(report_data: dict) -> str:
    return (
        "Write a monthly business summary for Meridian Automation Solutions leadership, "
        "based ONLY on the data below. 3 short paragraphs: (1) overall financial health, "
        "(2) sales and marketing performance, (3) customer intelligence and anything flagged "
        "as anomalous. Plain English, no jargon, no invented numbers beyond what's given.\n\n"
        f"DATA:\n{report_data}"
    )


def generate_report_narrative(report_data: dict) -> str:
    prompt = _build_narrative_prompt(report_data)
    for model_name in (chatbot.PRIMARY_MODEL, chatbot.FALLBACK_MODEL):
        config = types.GenerateContentConfig(
            system_instruction="You are writing a concise monthly business report narrative. Be factual and specific.",
            temperature=0.4,
            max_output_tokens=1024,
            thinking_config=chatbot.thinking_config_for(model_name),
        )
        try:
            response = chatbot._client.models.generate_content(model=model_name, contents=prompt, config=config)
            return response.text
        except Exception:
            continue
    return "(Narrative generation temporarily unavailable -- see the data summary below.)"


# ------------------------------------------------------------------
# 3. HTML rendering
# ------------------------------------------------------------------
def render_report_html(report_data: dict, narrative: str, causal_narrative: str = None) -> str:
    fin = report_data["finance"]
    sales = report_data["sales"]
    mkt = report_data["marketing"]
    cust = report_data["customer"]

    mom = f"{fin['revenue_mom_pct']:+.1f}%" if fin["revenue_mom_pct"] is not None else "N/A"

    causal_section = ""
    if causal_narrative:
        causal_section = f"""
        <h2 style="font-size: 15px; margin-top: 24px; color: #7c3aed;">Why This Happened (cross-module analysis)</h2>
        <p style="white-space: pre-line; line-height: 1.5; background: #f5f3ff; padding: 12px; border-radius: 6px;">{causal_narrative}</p>
        """

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #1f2937;">
        <h1 style="font-size: 20px; border-bottom: 2px solid #111827; padding-bottom: 8px;">
            RevenuePilot Monthly Report -- {fin['period']}
        </h1>
        <p style="white-space: pre-line; line-height: 1.5;">{narrative}</p>
        {causal_section}

        <h2 style="font-size: 15px; margin-top: 24px;">Finance</h2>
        <ul>
            <li>Revenue: ${fin['revenue']:,.0f} (MoM: {mom})</li>
            <li>Gross margin: {fin['gross_margin_pct']}%</li>
            <li>Operating profit: ${fin['operating_profit']:,.0f}</li>
            <li>Cash flow: ${fin['cash_flow']:,.0f}</li>
        </ul>

        <h2 style="font-size: 15px;">Sales &amp; Marketing</h2>
        <ul>
            <li>Top region this month: {sales['top_region_this_month']}</li>
            <li>Marketing spend this month: ${mkt['period_spend']:,.0f}, {mkt['period_conversions']} conversions</li>
            <li>Best ROI channel: {mkt['best_channel']} ({mkt['best_channel_roi']}x)</li>
            <li>Weakest ROI channel: {mkt['weakest_channel']} ({mkt['weakest_channel_roi']}x)</li>
        </ul>

        <h2 style="font-size: 15px;">Customer Intelligence</h2>
        <ul>
            <li>Total customers: {cust['total_customers']}</li>
            <li>High-risk churn: {cust['high_risk_churn_pct']}%</li>
            <li>Largest segment: {cust['top_segment']}</li>
        </ul>

        <h2 style="font-size: 15px;">Flagged this period</h2>
        <ul>
            <li>Finance anomalies (all-time): {report_data['finance_anomalies_total']}</li>
            <li>Sales anomalies: {sales['anomalies_flagged']}</li>
            <li>Marketing anomalies: {mkt['anomalies_flagged']}</li>
        </ul>

        <p style="color: #6b7280; font-size: 12px; margin-top: 24px;">
            Auto-generated by RevenuePilot. Data as of {fin['period']}.
        </p>
    </div>
    """


# ------------------------------------------------------------------
# 4. Sending
# ------------------------------------------------------------------
def send_report_email(to_emails: list, subject: str, html_body: str) -> dict:
    params = {
        "from": DEFAULT_FROM_ADDRESS,
        "to": to_emails,
        "subject": subject,
        "html": html_body,
    }
    return resend.Emails.send(params)


# ------------------------------------------------------------------
# 5. Convenience: build + send in one call
# ------------------------------------------------------------------
def build_and_send_monthly_report(bundle: dict, to_emails: list) -> dict:
    report_data = gather_monthly_report_data(bundle)
    narrative = generate_report_narrative(report_data)
    causal_narrative = generate_causal_narrative(bundle, report_data)
    html = render_report_html(report_data, narrative, causal_narrative)
    subject = f"RevenuePilot Monthly Report -- {report_data['finance']['period']}"
    try:
        send_result = send_report_email(to_emails, subject, html)
    except Exception as e:
        send_result = {"error": str(e)}
    return {"report_data": report_data, "narrative": narrative, "causal_narrative": causal_narrative, "send_result": send_result}


# ------------------------------------------------------------------
# 5b. Causal reasoning ("why" analysis) -- multi-month, time-lagged
# ------------------------------------------------------------------
def gather_causal_context(bundle: dict, lookback_months: int = 6) -> dict:
    """
    Builds MULTI-MONTH trend series (not just this-month-vs-last-month) so
    the model can reason about LAGGED cross-module effects -- e.g. a
    marketing spend or conversion change two months ago showing up as a
    revenue change now, accounting for a realistic B2B sales-cycle lag --
    rather than only ever comparing two adjacent snapshots.
    """
    finance = bundle["finance"].sort_values("month").tail(lookback_months).copy()
    finance["month"] = finance["month"].dt.strftime("%Y-%m")
    finance_trend = finance[["month", "revenue", "marketing_spend", "cogs", "operating_profit", "cash_flow"]].to_dict("records")

    marketing = bundle["marketing"].copy()
    monthly_marketing = (
        marketing.groupby("month")
        .agg(spend=("spend", "sum"), leads=("leads_generated", "sum"), conversions=("conversions", "sum"))
        .reset_index()
        .sort_values("month")
        .tail(lookback_months)
    )
    monthly_marketing["month"] = monthly_marketing["month"].dt.strftime("%Y-%m")
    marketing_trend = monthly_marketing.to_dict("records")

    sales = bundle["sales"].copy()
    sales["month"] = pd.to_datetime(sales["date"]).values.astype("datetime64[M]")
    monthly_sales = (
        sales.groupby("month")
        .agg(revenue=("revenue", "sum"), transactions=("transaction_id", "count"))
        .reset_index()
        .sort_values("month")
        .tail(lookback_months)
    )
    monthly_sales["month"] = monthly_sales["month"].dt.strftime("%Y-%m")
    sales_trend = monthly_sales.to_dict("records")

    # Per-channel trend for the top 3 channels by total spend -- lets the
    # model point to a SPECIFIC channel's dip/spike, not just "marketing" broadly.
    top_channels = marketing.groupby("channel")["spend"].sum().sort_values(ascending=False).head(3).index.tolist()
    channel_trends = {}
    for ch in top_channels:
        ch_df = marketing[marketing["channel"] == ch].sort_values("month").tail(lookback_months).copy()
        ch_df["month"] = ch_df["month"].dt.strftime("%Y-%m")
        channel_trends[ch] = ch_df[["month", "spend", "conversions"]].to_dict("records")

    fin_anom = bundle["finance_anomalies"].sort_values("month").tail(lookback_months).copy()
    fin_anom["month"] = pd.to_datetime(fin_anom["month"]).dt.strftime("%Y-%m")
    finance_anomalies_recent = fin_anom[["month", "is_anomaly", "anomaly_score"]].to_dict("records")

    return {
        "finance_trend": finance_trend,
        "marketing_trend": marketing_trend,
        "sales_trend": sales_trend,
        "top_channel_trends": channel_trends,
        "finance_anomalies_recent": finance_anomalies_recent,
    }


def _build_causal_narrative_prompt(causal_context: dict) -> str:
    return (
        f"Analyze the following {len(causal_context['finance_trend'])}-month trend data for "
        "Meridian Automation Solutions and write a CAUSAL analysis, not just a summary.\n\n"
        "Your task: identify PLAUSIBLE causal chains connecting marketing activity, sales, and "
        "finance across time -- for example, whether a change in marketing spend or conversions "
        "in an earlier month correlates with a change in revenue in a LATER month (accounting for "
        "a realistic 1-3 month B2B sales-cycle lag). Only claim a link if the trend data actually "
        "supports it. If the data is inconclusive, say so explicitly rather than inventing a story.\n\n"
        "Structure your answer as exactly three short parts:\n"
        "1. THIS MONTH'S HEADLINE: one sentence on what changed most notably this month.\n"
        "2. LIKELY CAUSE (if identifiable): trace it back through the monthly trends below -- "
        "name the specific month(s) and channel(s) involved. If no clear cause is visible in the "
        "data, state that plainly instead of speculating.\n"
        "3. WATCH FOR: one forward-looking risk or opportunity implied by the trend, if any.\n\n"
        "Keep the whole answer to 4-6 sentences total. Do not invent numbers not present below.\n\n"
        f"MONTHLY TREND DATA:\n"
        f"Finance (last {len(causal_context['finance_trend'])} months): {causal_context['finance_trend']}\n"
        f"Marketing totals: {causal_context['marketing_trend']}\n"
        f"Sales: {causal_context['sales_trend']}\n"
        f"Top 3 channels by spend, individual trends: {causal_context['top_channel_trends']}\n"
        f"Finance anomalies flagged in this window: {causal_context['finance_anomalies_recent']}"
    )


def generate_causal_narrative(bundle: dict, report_data: dict = None) -> str:
    """
    The deepened, multi-month causal reasoning pass. Deliberately kept
    SEPARATE from generate_report_narrative() above: that one is a plain
    factual summary (cheap, low-risk); this one asks the model to reason
    about time-lagged cause-and-effect, which needs a stricter prompt and
    more room to work, and is worth extra scrutiny on the output since a
    wrong causal claim is worse than a wrong summary.
    """
    causal_context = gather_causal_context(bundle)
    prompt = _build_causal_narrative_prompt(causal_context)
    for model_name in (chatbot.PRIMARY_MODEL, chatbot.FALLBACK_MODEL):
        config = types.GenerateContentConfig(
            system_instruction=(
                "You are a data analyst writing a causal analysis for company leadership. Reason "
                "carefully about time-lagged cause-and-effect using ONLY the provided trend data. "
                "Explicitly distinguish 'the data shows X' from 'this is uncertain' -- never state a "
                "causal claim as fact if the trend data doesn't clearly support it."
            ),
            temperature=0.3,
            max_output_tokens=1536,
            thinking_config=chatbot.thinking_config_for(model_name),  # keep off: see chatbot.py note re: truncation
        )
        try:
            response = chatbot._client.models.generate_content(model=model_name, contents=prompt, config=config)
            return response.text
        except Exception:
            continue
    return "(Causal analysis temporarily unavailable -- see the trend data in the sections below.)"


# ------------------------------------------------------------------
# 6. Department-scoped reports (admin gets everything, each department
#    gets only its own module's data) -- recipients pulled live from
#    the employees/departments tables via db.py, not typed by hand.
# ------------------------------------------------------------------
DEPARTMENT_TO_BLOCK = {
    "Sales": "sales",
    "Marketing": "marketing",
    "Finance": "finance",
    "Customer Intelligence": "customer",
}


def _narrative_for_block(department_name: str, block_name: str, block_data: dict) -> str:
    prompt = (
        f"Write a 2-paragraph monthly summary for the {department_name} team at Meridian "
        f"Automation Solutions, based ONLY on the data below. Plain English, specific numbers, "
        f"no invented figures.\n\nDATA ({block_name}):\n{block_data}"
    )
    for model_name in (chatbot.PRIMARY_MODEL, chatbot.FALLBACK_MODEL):
        config = types.GenerateContentConfig(
            system_instruction=f"You are writing a department-specific monthly report for the {department_name} team.",
            temperature=0.4,
            max_output_tokens=800,
            thinking_config=chatbot.thinking_config_for(model_name),
        )
        try:
            response = chatbot._client.models.generate_content(model=model_name, contents=prompt, config=config)
            return response.text
        except Exception:
            continue
    return "(Narrative generation temporarily unavailable -- see the data summary below.)"


def _render_department_html(department_name: str, period: str, block_data: dict, narrative: str) -> str:
    items = "".join(f"<li>{k.replace('_', ' ').title()}: {v}</li>" for k, v in block_data.items())
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #1f2937;">
        <h1 style="font-size: 20px; border-bottom: 2px solid #111827; padding-bottom: 8px;">
            {department_name} Monthly Report -- {period}
        </h1>
        <p style="white-space: pre-line; line-height: 1.5;">{narrative}</p>
        <h2 style="font-size: 15px; margin-top: 20px;">Key figures</h2>
        <ul>{items}</ul>
        <p style="color: #6b7280; font-size: 12px; margin-top: 24px;">
            Auto-generated by RevenuePilot for the {department_name} team.
        </p>
    </div>
    """


def send_all_reports(bundle: dict) -> dict:
    """
    Sends the full combined report to every admin. (Department-scoped
    delivery to individual employees was removed -- admin is the single
    point of distribution for now; the department-specific data slicing
    logic (DEPARTMENT_TO_BLOCK, _narrative_for_block, etc.) stays in this
    file since the KPI/performance feature still uses it internally, it's
    just no longer used to route separate emails.)
    """
    report_data = gather_monthly_report_data(bundle)
    period = report_data["finance"]["period"]
    results = {"admin": None}

    admin_rows = db.get_admin_emails()
    admin_emails = [r["email"] for r in admin_rows]
    if admin_emails:
        narrative = generate_report_narrative(report_data)
        causal_narrative = generate_causal_narrative(bundle, report_data)
        html = render_report_html(report_data, narrative, causal_narrative)
        subject = f"RevenuePilot Monthly Report (All Departments) -- {period}"
        try:
            send_result = send_report_email(admin_emails, subject, html)
            results["admin"] = {"recipients": admin_emails, "send_result": send_result}
        except Exception as e:
            results["admin"] = {"recipients": admin_emails, "error": str(e)}
    else:
        results["admin"] = {"recipients": [], "note": "No employees with role='admin' found -- run seed_org.py first."}

    return results
