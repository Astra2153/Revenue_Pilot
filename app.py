"""
app.py

RevenuePilot -- AI-Powered Sales, Marketing & Finance Analytics Platform.

A single Streamlit dashboard unifying sales, marketing, and finance data
with ML-driven revenue forecasting, RFM customer segmentation, and
churn-risk scoring, across four modules: Sales, Marketing, Finance, and
Customer Intelligence.

Sample deployment shown here: Meridian Automation Solutions, a B2B
industrial automation and robotics solutions provider.

Author: Ashmit Sanjay Katale
Run locally with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from data_generator import generate_all_data, current_month_start, COMPANY_NAME
from analytics import (
    RevenueForecaster,
    CustomerSegmenter,
    ChurnScorer,
    compute_marketing_roi,
    generate_insights,
)

# ----------------------------------------------------------------------
# Page config & light styling
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="RevenuePilot | Sales, Marketing & Finance Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .metric-card {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e6e6e6;
    }
    .insight-box {
        background-color: #f0f7ff;
        border-left: 4px solid #2563eb;
        padding: 0.85rem 1rem;
        border-radius: 0.35rem;
        margin-bottom: 0.6rem;
        font-size: 0.95rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
    }
    footer {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Cached data + model pipeline
# ----------------------------------------------------------------------
@st.cache_data(show_spinner="Generating synthetic business data...")
def load_data(n_customers: int, months_back: int, seed: int):
    return generate_all_data(n_customers=n_customers, months_back=months_back, seed=seed)


@st.cache_data(show_spinner="Training forecasting model...")
def run_forecast(finance_df: pd.DataFrame, periods: int, _seed: int):
    forecaster = RevenueForecaster(random_state=_seed)
    forecaster.fit(finance_df)
    forecast_df = forecaster.forecast(periods=periods)
    return forecast_df, forecaster.metrics_, forecaster.feature_importances()


@st.cache_data(show_spinner="Running customer segmentation...")
def run_segmentation(sales_df: pd.DataFrame, customers_df: pd.DataFrame, n_clusters: int, _seed: int):
    segmenter = CustomerSegmenter(n_clusters=n_clusters, random_state=_seed)
    rfm_result = segmenter.fit_predict(sales_df, customers_df)
    seg_summary = segmenter.segment_summary(rfm_result)
    return rfm_result, seg_summary


@st.cache_data(show_spinner="Scoring churn risk...")
def run_churn_scoring(rfm_result: pd.DataFrame, _seed: int):
    scorer = ChurnScorer(random_state=_seed)
    churn_result = scorer.fit_predict(rfm_result)
    return churn_result, scorer.metrics_, scorer.feature_importances()


# ----------------------------------------------------------------------
# Sidebar controls
# ----------------------------------------------------------------------
st.sidebar.title("RevenuePilot")
st.sidebar.caption("AI-Powered Sales, Marketing & Finance Analytics")

st.sidebar.markdown("### Data Settings")
n_customers = st.sidebar.slider("Number of customers", 100, 800, 400, step=50)
months_back = st.sidebar.slider("Months of history", 12, 36, 24, step=6)
forecast_periods = st.sidebar.slider("Forecast horizon (months)", 3, 12, 6, step=1)
n_clusters = st.sidebar.slider("Customer segments (K-Means clusters)", 3, 6, 4, step=1)
seed = st.sidebar.number_input("Random seed", min_value=0, max_value=9999, value=42, step=1)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**About this deployment**\n\n"
    f"This instance of RevenuePilot is configured for {COMPANY_NAME}, an industrial "
    f"automation and robotics solutions provider, consolidating its sales, marketing, "
    f"and finance data into one view. Point it at a different dataset with the same "
    f"schema to deploy it for another business."
)
st.sidebar.markdown("Built with Python, Streamlit, scikit-learn, Plotly, Pandas")
st.sidebar.caption("Developed by Ashmit Sanjay Katale")

# ----------------------------------------------------------------------
# Load data + run pipeline
# ----------------------------------------------------------------------
customers, sales, marketing, finance = load_data(n_customers, months_back, seed)
forecast_df, forecast_metrics, forecast_importances = run_forecast(finance, forecast_periods, seed)
rfm_result, seg_summary = run_segmentation(sales, customers, n_clusters, seed)
churn_result, churn_metrics, churn_importances = run_churn_scoring(rfm_result, seed)

avg_customer_value = rfm_result["monetary"].median()
roi_summary = compute_marketing_roi(marketing, avg_customer_value)

insights = generate_insights(sales, marketing, finance, rfm_result, churn_result, roi_summary, forecast_df)

CUTOFF = current_month_start()
sales_complete = sales[pd.to_datetime(sales["date"]) < CUTOFF]
marketing_complete = marketing[marketing["month"] < CUTOFF]

# ----------------------------------------------------------------------
# Header + top-line KPIs
# ----------------------------------------------------------------------
st.title("RevenuePilot")
st.markdown(f"##### AI-Powered Sales, Marketing & Finance Analytics Platform | {COMPANY_NAME}")
st.caption(
    "Unifying sales, marketing, and finance data into one dashboard with ML-driven revenue forecasting, "
    "RFM customer segmentation, and churn-risk scoring."
)

latest_month = finance.sort_values("month").iloc[-1]
total_revenue_ttm = finance.sort_values("month").tail(12)["revenue"].sum()
total_customers = len(rfm_result)
high_risk_count = int((churn_result["churn_risk"] == "High Risk").sum())

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Latest Monthly Revenue", f"${latest_month['revenue']:,.0f}")
kpi2.metric("Trailing 12-Month Revenue", f"${total_revenue_ttm:,.0f}")
kpi3.metric("Operating Margin", f"{(latest_month['operating_profit'] / latest_month['revenue'] * 100):.1f}%")
kpi4.metric("Total Customers", f"{total_customers:,}")
kpi5.metric("High Churn-Risk Customers", f"{high_risk_count:,}", delta=f"{high_risk_count/total_customers*100:.1f}% of base", delta_color="inverse")

st.markdown("---")

# ----------------------------------------------------------------------
# Tabs: Sales | Marketing | Finance | Customer Intelligence
# ----------------------------------------------------------------------
tab_sales, tab_marketing, tab_finance, tab_customer = st.tabs(
    ["Sales", "Marketing", "Finance", "Customer Intelligence"]
)

# =========================================================
# TAB 1: SALES
# =========================================================
with tab_sales:
    st.subheader("Sales Performance & Revenue Forecasting")

    left, right = st.columns([2, 1])

    with left:
        monthly_sales = (
            sales_complete.assign(month=pd.to_datetime(sales_complete["date"]).values.astype("datetime64[M]"))
            .groupby("month")["revenue"].sum().reset_index()
        )
        forecast_plot_df = forecast_df.rename(columns={"forecast_revenue": "revenue"})
        forecast_plot_df["type"] = "Forecast"
        monthly_sales["type"] = "Actual"
        combined = pd.concat([monthly_sales, forecast_plot_df], ignore_index=True)

        fig = go.Figure()
        actual = combined[combined["type"] == "Actual"]
        fcst = combined[combined["type"] == "Forecast"]
        fig.add_trace(go.Scatter(x=actual["month"], y=actual["revenue"], mode="lines+markers", name="Actual Revenue", line=dict(color="#2563eb", width=3)))
        # bridge the line from last actual point to first forecast point
        bridge_x = [actual["month"].iloc[-1], fcst["month"].iloc[0]] if not fcst.empty else []
        bridge_y = [actual["revenue"].iloc[-1], fcst["revenue"].iloc[0]] if not fcst.empty else []
        fig.add_trace(go.Scatter(x=bridge_x, y=bridge_y, mode="lines", line=dict(color="#f59e0b", width=3, dash="dot"), showlegend=False))
        fig.add_trace(go.Scatter(x=fcst["month"], y=fcst["revenue"], mode="lines+markers", name="Forecast (RandomForest)", line=dict(color="#f59e0b", width=3, dash="dot")))
        fig.update_layout(title="Monthly Revenue: Actual vs. Forecast", height=420, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

        if forecast_metrics.get("mae") is not None:
            st.caption(
                f"Forecast validation (holdout set, {forecast_metrics['test_size']} months): "
                f"Mean Absolute Error ≈ ${forecast_metrics['mae']:,.0f}."
            )

    with right:
        st.markdown("**What drives the forecast?**")
        imp_fig = px.bar(
            forecast_importances, x="importance", y="feature", orientation="h",
            title="Forecast Feature Importance", color="importance", color_continuous_scale="Blues"
        )
        imp_fig.update_layout(height=420, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(imp_fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        region_rev = sales_complete.groupby("region")["revenue"].sum().reset_index().sort_values("revenue", ascending=False)
        fig_region = px.bar(region_rev, x="revenue", y="region", orientation="h", title="Revenue by Region", color="revenue", color_continuous_scale="Teal")
        fig_region.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig_region, use_container_width=True)

    with col_b:
        cat_rev = sales_complete.groupby("product_category")["revenue"].sum().reset_index().sort_values("revenue", ascending=False)
        fig_cat = px.pie(cat_rev, names="product_category", values="revenue", title="Revenue by Product Category", hole=0.45)
        fig_cat.update_layout(height=350)
        st.plotly_chart(fig_cat, use_container_width=True)

    channel_rev = sales_complete.groupby("sales_channel")["revenue"].sum().reset_index().sort_values("revenue", ascending=False)
    fig_channel = px.bar(channel_rev, x="sales_channel", y="revenue", title="Revenue by Sales Channel", color="revenue", color_continuous_scale="Purples")
    fig_channel.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_channel, use_container_width=True)

    st.markdown("#### Auto-Generated Insights")
    for bullet in insights["sales"]:
        st.markdown(f'<div class="insight-box">{bullet}</div>', unsafe_allow_html=True)

# =========================================================
# TAB 2: MARKETING
# =========================================================
with tab_marketing:
    st.subheader("Marketing Channel Performance & ROI")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Marketing Spend", f"${marketing_complete['spend'].sum():,.0f}")
    m2.metric("Total Conversions", f"{int(marketing_complete['conversions'].sum()):,}")
    blended_cac = marketing_complete["spend"].sum() / marketing_complete["conversions"].sum()
    m3.metric("Blended CAC", f"${blended_cac:,.0f}")
    m4.metric("Best-ROI Channel", roi_summary.iloc[0]["channel"])

    left, right = st.columns(2)
    with left:
        fig_roi = px.bar(
            roi_summary.sort_values("roi_multiple"), x="roi_multiple", y="channel", orientation="h",
            title="Estimated ROI Multiple by Channel", color="roi_multiple", color_continuous_scale="RdYlGn",
            labels={"roi_multiple": "ROI (x)", "channel": ""}
        )
        fig_roi.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig_roi, use_container_width=True)

    with right:
        fig_cac = px.bar(
            roi_summary.sort_values("cac"), x="cac", y="channel", orientation="h",
            title="Customer Acquisition Cost (CAC) by Channel", color="cac", color_continuous_scale="OrRd",
            labels={"cac": "CAC ($)", "channel": ""}
        )
        fig_cac.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig_cac, use_container_width=True)

    monthly_channel = marketing_complete.groupby(["month", "channel"])["spend"].sum().reset_index()
    fig_spend_trend = px.area(monthly_channel, x="month", y="spend", color="channel", title="Monthly Marketing Spend by Channel")
    fig_spend_trend.update_layout(height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig_spend_trend, use_container_width=True)

    funnel_totals = marketing_complete[["impressions", "clicks", "leads_generated", "conversions"]].sum()
    fig_funnel = go.Figure(go.Funnel(
        y=["Impressions", "Clicks", "Leads Generated", "Conversions"],
        x=[funnel_totals["impressions"], funnel_totals["clicks"], funnel_totals["leads_generated"], funnel_totals["conversions"]],
        marker=dict(color=["#93c5fd", "#60a5fa", "#3b82f6", "#1d4ed8"])
    ))
    fig_funnel.update_layout(title="Overall Marketing Funnel (All Channels Combined)", height=400)
    st.plotly_chart(fig_funnel, use_container_width=True)

    st.markdown("**Channel Detail Table**")
    display_roi = roi_summary.rename(columns={
        "channel": "Channel", "total_spend": "Total Spend ($)", "total_leads": "Total Leads",
        "total_conversions": "Total Conversions", "cac": "CAC ($)",
        "estimated_value_generated": "Est. Value Generated ($)", "roi_multiple": "ROI (x)",
        "conversion_rate": "Lead→Conversion Rate"
    })
    st.dataframe(display_roi, use_container_width=True, hide_index=True)
    st.caption(
        "Est. Value Generated = conversions × median customer lifetime value (from the RFM table)."
    )

    st.markdown("#### Auto-Generated Insights")
    for bullet in insights["marketing"]:
        st.markdown(f'<div class="insight-box">{bullet}</div>', unsafe_allow_html=True)

# =========================================================
# TAB 3: FINANCE
# =========================================================
with tab_finance:
    st.subheader("Financial Overview")

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Latest Revenue", f"${latest_month['revenue']:,.0f}")
    f1_gm = latest_month["gross_profit"] / latest_month["revenue"] * 100
    f2.metric("Gross Margin", f"{f1_gm:.1f}%")
    f2_om = latest_month["operating_profit"] / latest_month["revenue"] * 100
    f3.metric("Operating Margin", f"{f2_om:.1f}%")
    f4.metric("Latest Cash Flow", f"${latest_month['cash_flow']:,.0f}")

    finance_sorted = finance.sort_values("month")

    fig_waterfall_months = finance_sorted.tail(6)
    fig_pl = go.Figure()
    fig_pl.add_trace(go.Bar(x=fig_waterfall_months["month"], y=fig_waterfall_months["revenue"], name="Revenue", marker_color="#2563eb"))
    fig_pl.add_trace(go.Bar(x=fig_waterfall_months["month"], y=fig_waterfall_months["cogs"], name="COGS", marker_color="#f97316"))
    fig_pl.add_trace(go.Bar(x=fig_waterfall_months["month"], y=fig_waterfall_months["marketing_spend"], name="Marketing Spend", marker_color="#a855f7"))
    fig_pl.add_trace(go.Bar(x=fig_waterfall_months["month"], y=fig_waterfall_months["other_opex"], name="Other Opex", marker_color="#94a3b8"))
    fig_pl.update_layout(title="Revenue vs. Cost Breakdown (Last 6 Months)", barmode="group", height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig_pl, use_container_width=True)

    left, right = st.columns(2)
    with left:
        fig_margin = go.Figure()
        fig_margin.add_trace(go.Scatter(x=finance_sorted["month"], y=(finance_sorted["gross_profit"] / finance_sorted["revenue"] * 100), name="Gross Margin %", line=dict(color="#16a34a", width=3)))
        fig_margin.add_trace(go.Scatter(x=finance_sorted["month"], y=(finance_sorted["operating_profit"] / finance_sorted["revenue"] * 100), name="Operating Margin %", line=dict(color="#2563eb", width=3)))
        fig_margin.update_layout(title="Margin Trends Over Time", height=380, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_margin, use_container_width=True)

    with right:
        fig_cash = px.bar(finance_sorted, x="month", y="cash_flow", title="Monthly Cash Flow", color="cash_flow", color_continuous_scale="RdYlGn")
        fig_cash.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig_cash, use_container_width=True)

    st.markdown("**Monthly Finance Detail**")
    display_finance = finance_sorted.rename(columns={
        "month": "Month", "revenue": "Revenue", "marketing_spend": "Marketing Spend", "cogs": "COGS",
        "gross_profit": "Gross Profit", "other_opex": "Other Opex", "operating_profit": "Operating Profit",
        "cash_flow": "Cash Flow"
    }).copy()
    display_finance["Month"] = display_finance["Month"].dt.strftime("%b %Y")
    st.dataframe(display_finance.set_index("Month").style.format("${:,.0f}"), use_container_width=True)

    st.markdown("#### Auto-Generated Insights")
    for bullet in insights["finance"]:
        st.markdown(f'<div class="insight-box">{bullet}</div>', unsafe_allow_html=True)

# =========================================================
# TAB 4: CUSTOMER INTELLIGENCE
# =========================================================
with tab_customer:
    st.subheader("Customer Intelligence: RFM Segmentation & Churn Risk")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Customers", f"{len(rfm_result):,}")
    c2.metric("Segments Identified", f"{rfm_result['segment_label'].nunique()}")
    c3.metric("High Churn Risk", f"{(churn_result['churn_risk'] == 'High Risk').sum():,}")
    if churn_metrics.get("accuracy") is not None:
        c4.metric("Churn Model Accuracy (holdout)", f"{churn_metrics['accuracy']*100:.1f}%")
    else:
        c4.metric("Churn Model", "Rule-based fallback")

    left, right = st.columns([3, 2])
    with left:
        fig_rfm = px.scatter(
            rfm_result, x="recency_days", y="monetary", size="frequency", color="segment_label",
            hover_data=["customer_id", "frequency"], title="Customer Segments (RFM: Recency vs. Monetary, sized by Frequency)",
            log_y=True, labels={"recency_days": "Days Since Last Purchase", "monetary": "Total Spend ($, log scale)"}
        )
        fig_rfm.update_layout(height=460, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_rfm, use_container_width=True)

    with right:
        seg_counts = rfm_result["segment_label"].value_counts().reset_index()
        seg_counts.columns = ["segment_label", "count"]
        fig_seg_pie = px.pie(seg_counts, names="segment_label", values="count", title="Customer Segment Distribution", hole=0.45)
        fig_seg_pie.update_layout(height=460)
        st.plotly_chart(fig_seg_pie, use_container_width=True)

    st.markdown("**Segment Summary**")
    display_seg = seg_summary.rename(columns={
        "segment_label": "Segment", "customers": "Customers", "avg_recency_days": "Avg Recency (days)",
        "avg_frequency": "Avg Frequency (orders)", "avg_monetary": "Avg Spend ($)", "total_monetary": "Total Segment Value ($)"
    })
    st.dataframe(display_seg, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Churn Risk Breakdown**")

    left2, right2 = st.columns([2, 3])
    with left2:
        risk_counts = churn_result["churn_risk"].value_counts().reindex(["Low Risk", "Medium Risk", "High Risk"]).fillna(0).reset_index()
        risk_counts.columns = ["Risk Level", "Customers"]
        fig_risk = px.bar(
            risk_counts, x="Risk Level", y="Customers", color="Risk Level", title="Customers by Churn Risk Level",
            color_discrete_map={"Low Risk": "#16a34a", "Medium Risk": "#f59e0b", "High Risk": "#dc2626"}
        )
        fig_risk.update_layout(height=380, showlegend=False)
        st.plotly_chart(fig_risk, use_container_width=True)

    with right2:
        fig_churn_imp = px.bar(
            churn_importances, x="importance", y="feature", orientation="h",
            title="What Predicts Churn? (Model Feature Importance)", color="importance", color_continuous_scale="Reds"
        )
        fig_churn_imp.update_layout(height=380, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig_churn_imp, use_container_width=True)

    st.markdown("**Highest-Value Customers at Risk** _(sorted by historical spend, High Risk only)_")
    at_risk_high_value = (
        churn_result[churn_result["churn_risk"] == "High Risk"]
        .sort_values("monetary", ascending=False)
        .head(10)[["customer_id", "segment", "region", "recency_days", "frequency", "monetary", "churn_probability"]]
    )
    at_risk_high_value = at_risk_high_value.rename(columns={
        "customer_id": "Customer ID", "segment": "Segment", "region": "Region",
        "recency_days": "Days Since Last Purchase", "frequency": "Total Orders",
        "monetary": "Lifetime Spend ($)", "churn_probability": "Churn Probability"
    })
    st.dataframe(
        at_risk_high_value.style.format({"Lifetime Spend ($)": "${:,.0f}", "Churn Probability": "{:.1%}"}),
        use_container_width=True, hide_index=True
    )
    st.caption(
        "Customers are labeled at risk if they have not purchased in over 120 days; the "
        "RandomForestClassifier is trained on RFM features to predict this label."
    )

    st.markdown("#### Auto-Generated Insights")
    for bullet in insights["customer"]:
        st.markdown(f'<div class="insight-box">{bullet}</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Footer
# ----------------------------------------------------------------------
st.markdown("---")
st.caption(
    "RevenuePilot | Developed by Ashmit Sanjay Katale | "
    "Built with Python, Streamlit, scikit-learn, Plotly & Pandas."
)
