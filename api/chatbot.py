"""
chatbot.py

Gemini-powered chatbot for RevenuePilot. Rather than sending raw rows of
sales/marketing/finance/customer data to the model (slow, expensive, and
mostly irrelevant per-question), this builds a COMPACT, pre-computed
summary from results your API already calculates (forecast, ROI, RFM,
churn, anomalies, cohorts, insights) -- scoped to whichever business
module the question is about -- and grounds the model's answer in that.

Uses the current official Google Gen AI SDK (`google-genai`), NOT the
deprecated `google-generativeai` package.

Requires GEMINI_API_KEY in your .env file (from Google AI Studio).
"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY. Add it to your .env file (from Google AI Studio).")

# Primary model, with a cheaper/more-available fallback if the primary
# hits a free-tier rate limit. Google retires older model generations for
# new accounts periodically -- if you ever see a 404 "model no longer
# available" error, check ai.google.dev/gemini-api/docs/models for the
# current model names and update these two constants.
PRIMARY_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

_client = genai.Client(api_key=GEMINI_API_KEY)


def thinking_config_for(model_name: str) -> types.ThinkingConfig:
    """
    Gemini 3.x's "-lite" model variants validate thinking config differently
    from the base models -- they expect thinking_level, not thinking_budget,
    and reject the older parameter with a 400 INVALID_ARGUMENT (confirmed via
    a real failure during testing: the base model accepted thinking_budget=0
    fine, but the lite fallback rejected it outright). Shared here so every
    caller (chatbot.py, report.py, kpi.py) that loops over PRIMARY_MODEL and
    FALLBACK_MODEL gets a config each model will actually accept, instead of
    each file guessing its own fix.
    """
    if "lite" in model_name:
        return types.ThinkingConfig(thinking_level="MINIMAL")
    return types.ThinkingConfig(thinking_budget=0)


MODULES = {"sales", "marketing", "finance", "customer"}


def build_context_summary(bundle: dict, module: str = None) -> str:
    """
    Builds a short, plain-text grounding summary from the already-computed
    analytics bundle (the same `data` dict api.py's get_data() produces).
    `module` scopes it to one of MODULES; None/omitted returns all four,
    condensed.
    """
    lines = []

    def sales_section():
        finance = bundle["finance"]
        latest_rev = finance.sort_values("month")["revenue"].iloc[-1]
        top_region = bundle["sales"].groupby("region")["revenue"].sum().idxmax()
        fc = bundle["forecaster"].forecast(periods=3)
        lines.append(f"SALES: latest monthly revenue ${latest_rev:,.0f}. Top region by revenue: {top_region}.")
        lines.append("Forecast next 3 months (revenue): " + ", ".join(
            f"{r['month'].strftime('%b %Y')}=${r['forecast_revenue']:,.0f}" for _, r in fc.iterrows()
        ))
        n_anom = int(bundle["sales_anomalies"]["is_anomaly"].sum())
        lines.append(f"{n_anom} unusual individual transactions flagged by anomaly detection.")

    def marketing_section():
        roi = bundle["roi_summary"]
        best = roi.iloc[0]
        worst = roi.sort_values("roi_multiple").iloc[0]
        lines.append(
            f"MARKETING: best ROI channel is {best['channel']} ({best['roi_multiple']:.1f}x, "
            f"CAC ${best['cac']:,.0f}). Weakest is {worst['channel']} ({worst['roi_multiple']:.1f}x)."
        )
        n_anom = int(bundle["marketing_anomalies"]["is_anomaly"].sum())
        lines.append(f"{n_anom} channel-months flagged as anomalous (unusual CAC/conversion patterns).")

    def finance_section():
        latest = bundle["finance"].sort_values("month").iloc[-1]
        gross_margin = latest["gross_profit"] / latest["revenue"] * 100 if latest["revenue"] else 0
        op_margin = latest["operating_profit"] / latest["revenue"] * 100 if latest["revenue"] else 0
        lines.append(
            f"FINANCE: latest month revenue ${latest['revenue']:,.0f}, gross margin {gross_margin:.1f}%, "
            f"operating margin {op_margin:.1f}%, cash flow ${latest['cash_flow']:,.0f}."
        )
        n_anom = int(bundle["finance_anomalies"]["is_anomaly"].sum())
        lines.append(f"{n_anom} months flagged as financially anomalous out of {len(bundle['finance'])} total.")

    def customer_section():
        rfm = bundle["rfm_result"]
        seg_counts = rfm["segment_label"].value_counts(normalize=True) * 100
        top_seg = seg_counts.idxmax()
        churn = bundle["churn_result"]
        high_risk_pct = (churn["churn_risk"] == "High Risk").mean() * 100
        lines.append(
            f"CUSTOMER INTELLIGENCE: largest segment is {top_seg} ({seg_counts.max():.1f}% of customers). "
            f"{high_risk_pct:.1f}% of customers are flagged High Risk for churn."
        )

    section_map = {
        "sales": sales_section,
        "marketing": marketing_section,
        "finance": finance_section,
        "customer": customer_section,
    }

    if module and module in section_map:
        section_map[module]()
    else:
        for fn in section_map.values():
            fn()

    return "\n".join(lines)


def _system_instruction(module: str = None) -> str:
    scope = f"the {module} module" if module in MODULES else "sales, marketing, finance, and customer intelligence"
    return (
        "You are the RevenuePilot analytics assistant for Meridian Automation Solutions. "
        f"You answer questions about {scope}, grounded ONLY in the data summary provided below. "
        "Be concise (2-4 sentences unless asked for detail). If the summary doesn't contain the "
        "answer, say so plainly rather than guessing or inventing numbers. Never fabricate figures "
        "that aren't in the provided summary."
    )


def ask(message: str, bundle: dict, module: str = None) -> dict:
    """
    Sends a question to Gemini, grounded in a context summary built from
    the current analytics bundle. Returns {"response": str, "model_used": str}.
    Falls back to FALLBACK_MODEL on a rate-limit/quota error from PRIMARY_MODEL.
    """
    context = build_context_summary(bundle, module)
    system_instruction = _system_instruction(module)
    prompt = f"DATA SUMMARY:\n{context}\n\nQUESTION: {message}"

    for model_name in (PRIMARY_MODEL, FALLBACK_MODEL):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            max_output_tokens=1024,
            # These are short, grounded factual answers, not complex multi-step
            # reasoning -- disable "thinking" so its internal reasoning tokens
            # don't eat into max_output_tokens and truncate the visible answer.
            thinking_config=thinking_config_for(model_name),
        )
        try:
            response = _client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return {"response": response.text, "model_used": model_name}
        except Exception as e:
            last_error = str(e)
            continue  # try the fallback model

    return {"response": f"Sorry, the chatbot is temporarily unavailable ({last_error}).", "model_used": None}
