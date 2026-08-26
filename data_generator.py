"""
data_generator.py

Generates the underlying sales, marketing, and finance data used by
RevenuePilot for Meridian Automation Solutions, a B2B industrial
automation and robotics solutions provider (hardware, software
licensing, cloud/IoT services, support, and consulting) serving
customers across five global regions.

Produces three linked datasets:
    1. Sales transactions   (customer purchases over time)
    2. Marketing campaigns  (spend, channel, leads, conversions)
    3. Finance records      (monthly revenue, COGS, opex, cash flow)

A fixed random seed keeps results reproducible across runs. Seasonality,
customer churn, and channel-level cost benchmarks are built in so the
forecasting, segmentation, and churn models have real patterns to learn.

Author: Ashmit Sanjay Katale
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

COMPANY_NAME = "Meridian Automation Solutions"

# ----------------------------------------------------------------------
# Reference data pools used to keep generated records realistic
# ----------------------------------------------------------------------
REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East & Africa"]
PRODUCT_CATEGORIES = ["Hardware", "Software Licenses", "Cloud Services", "Support & Maintenance", "Consulting"]
SALES_CHANNELS = ["Direct Sales", "Online Store", "Partner/Reseller", "Enterprise Deal"]
MARKETING_CHANNELS = ["Google Ads", "LinkedIn Ads", "Email Campaigns", "Content/SEO", "Trade Shows", "Referral Program"]
CUSTOMER_SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]


def _seasonal_multiplier(month: int) -> float:
    """Returns a seasonality multiplier by calendar month (1-12).
    Mimics real B2B patterns: Q4 push, summer slowdown, January dip."""
    seasonality = {
        1: 0.85, 2: 0.90, 3: 1.00, 4: 1.05, 5: 1.05, 6: 0.95,
        7: 0.85, 8: 0.90, 9: 1.05, 10: 1.15, 11: 1.20, 12: 1.30
    }
    return seasonality[month]


def generate_customers(n_customers: int = 400, seed: int = 42) -> pd.DataFrame:
    """Generates a base customer master table."""
    rng = np.random.default_rng(seed)

    customer_ids = [f"CUST-{i:05d}" for i in range(1, n_customers + 1)]
    segments = rng.choice(CUSTOMER_SEGMENTS, size=n_customers, p=[0.55, 0.30, 0.15])
    regions = rng.choice(REGIONS, size=n_customers)

    # Enterprise customers tend to join earlier (longer relationships)
    signup_days_ago = []
    for seg in segments:
        if seg == "Enterprise":
            signup_days_ago.append(int(rng.integers(400, 900)))
        elif seg == "Mid-Market":
            signup_days_ago.append(int(rng.integers(150, 600)))
        else:
            signup_days_ago.append(int(rng.integers(1, 400)))

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    signup_dates = [today - timedelta(days=d) for d in signup_days_ago]

    df = pd.DataFrame({
        "customer_id": customer_ids,
        "segment": segments,
        "region": regions,
        "signup_date": signup_dates,
    })
    return df


def generate_sales_data(customers: pd.DataFrame, months_back: int = 24, seed: int = 42) -> pd.DataFrame:
    """
    Generates individual sales transactions per customer over the trailing
    `months_back` months. Volume/value scale with customer segment, region,
    and seasonality, with some customers intentionally 'churning' (no
    recent purchases) so churn scoring has genuine signal to detect.
    """
    rng = np.random.default_rng(seed)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - timedelta(days=months_back * 30)

    segment_base_value = {"SMB": 800, "Mid-Market": 3500, "Enterprise": 15000}
    segment_txn_rate = {"SMB": 0.6, "Mid-Market": 1.1, "Enterprise": 1.8}  # avg txns/month

    records = []
    for _, cust in customers.iterrows():
        cust_signup = cust["signup_date"]
        effective_start = max(cust_signup, start_date)
        active_months = max(1, int((today - effective_start).days / 30))

        base_value = segment_base_value[cust["segment"]]
        txn_rate = segment_txn_rate[cust["segment"]]

        # ~18% of customers are "at risk" churners: activity stops partway through the window
        is_churning = rng.random() < 0.18
        churn_cutoff_month = rng.integers(2, max(3, active_months)) if is_churning and active_months > 3 else None

        for m in range(active_months):
            txn_month_date = effective_start + timedelta(days=m * 30)
            if txn_month_date > today:
                break
            if churn_cutoff_month is not None and m > churn_cutoff_month:
                continue  # customer has gone silent (churn signal)

            n_txns = rng.poisson(lam=txn_rate)
            for _ in range(n_txns):
                day_offset = rng.integers(0, 28)
                txn_date = txn_month_date + timedelta(days=int(day_offset))
                if txn_date > today:
                    continue

                seasonal = _seasonal_multiplier(txn_date.month)
                noise = rng.normal(1.0, 0.25)
                value = max(50, base_value * seasonal * noise * rng.uniform(0.5, 1.8))

                records.append({
                    "transaction_id": f"TXN-{len(records)+1:06d}",
                    "customer_id": cust["customer_id"],
                    "segment": cust["segment"],
                    "region": cust["region"],
                    "date": txn_date,
                    "product_category": rng.choice(PRODUCT_CATEGORIES),
                    "sales_channel": rng.choice(SALES_CHANNELS),
                    "revenue": round(float(value), 2),
                    "units_sold": int(rng.integers(1, 25)),
                })

    df = pd.DataFrame(records)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def generate_marketing_data(months_back: int = 24, seed: int = 42) -> pd.DataFrame:
    """
    Generates monthly marketing campaign performance data per channel:
    spend, impressions, clicks, leads generated, and conversions.

    Design note: conversions are derived from spend divided by a
    channel-specific target CAC range (grounded in realistic B2B
    benchmarks), and impressions/clicks/leads are then back-derived from
    conversions using channel-specific funnel rates. This guarantees a
    believable, internally consistent funnel (impressions >= clicks >=
    leads >= conversions) AND realistic cost-per-acquisition by channel,
    rather than letting funnel math accidentally produce a near-zero CAC.
    """
    rng = np.random.default_rng(seed + 1)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # cac_range: realistic cost-per-conversion band ($) for this channel type.
    # conv_rate_range: leads -> conversions rate. lead_rate_range: clicks -> leads rate.
    # ctr_range: impressions -> clicks rate (used loosely as "engagement rate" for
    # non-paid channels like trade shows/referrals, where it still yields a
    # sensible funnel shape even though there's no literal CPC auction).
    channel_profile = {
        "Google Ads":       {"base_spend": 12000, "cac_range": (350, 650),   "conv_rate_range": (0.08, 0.15), "lead_rate_range": (0.06, 0.12), "ctr_range": (0.020, 0.045)},
        "LinkedIn Ads":     {"base_spend": 9000,  "cac_range": (600, 1000),  "conv_rate_range": (0.10, 0.18), "lead_rate_range": (0.05, 0.10), "ctr_range": (0.015, 0.035)},
        "Email Campaigns":  {"base_spend": 2000,  "cac_range": (180, 380),  "conv_rate_range": (0.07, 0.13), "lead_rate_range": (0.10, 0.18), "ctr_range": (0.06, 0.11)},
        "Content/SEO":      {"base_spend": 4000,  "cac_range": (350, 650),  "conv_rate_range": (0.05, 0.10), "lead_rate_range": (0.05, 0.09), "ctr_range": (0.02, 0.04)},
        "Trade Shows":      {"base_spend": 18000, "cac_range": (1400, 2400),"conv_rate_range": (0.15, 0.24), "lead_rate_range": (0.30, 0.50), "ctr_range": (0.35, 0.55)},
        "Referral Program": {"base_spend": 3000,  "cac_range": (150, 320),  "conv_rate_range": (0.22, 0.35), "lead_rate_range": (0.35, 0.55), "ctr_range": (0.45, 0.65)},
    }

    records = []
    for m_back in range(months_back, 0, -1):
        month_date = (today.replace(day=1) - timedelta(days=m_back * 30)).replace(day=1)
        seasonal = _seasonal_multiplier(month_date.month)

        for channel, prof in channel_profile.items():
            spend = max(200, prof["base_spend"] * seasonal * rng.normal(1.0, 0.15))

            cac = rng.uniform(*prof["cac_range"])
            conversions = max(1, round(spend / cac))

            conv_rate = rng.uniform(*prof["conv_rate_range"])
            leads = max(conversions, round(conversions / conv_rate))

            lead_rate = rng.uniform(*prof["lead_rate_range"])
            clicks = max(leads, round(leads / lead_rate))

            ctr = rng.uniform(*prof["ctr_range"])
            impressions = max(clicks, round(clicks / ctr))

            records.append({
                "month": month_date.strftime("%Y-%m"),
                "channel": channel,
                "spend": round(float(spend), 2),
                "impressions": int(impressions),
                "clicks": int(clicks),
                "leads_generated": int(leads),
                "conversions": int(conversions),
            })

    df = pd.DataFrame(records)
    df["month"] = pd.to_datetime(df["month"])
    df = df.sort_values(["month", "channel"]).reset_index(drop=True)
    return df


def generate_finance_data(sales_df: pd.DataFrame, marketing_df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """
    Derives a monthly finance table (revenue, COGS, gross profit, marketing
    spend, other opex, operating profit, cash flow) from the sales and
    marketing datasets so all three modules stay numerically consistent.
    """
    rng = np.random.default_rng(seed + 2)

    monthly_revenue = (
        sales_df.assign(month=pd.to_datetime(sales_df["date"]).values.astype("datetime64[M]"))
        .groupby("month")["revenue"].sum()
        .rename("revenue")
    )
    monthly_marketing_spend = marketing_df.groupby("month")["spend"].sum().rename("marketing_spend")

    finance = pd.concat([monthly_revenue, monthly_marketing_spend], axis=1, sort=True).fillna(0).reset_index()
    finance = finance.rename(columns={"index": "month"})
    finance = finance.sort_values("month").reset_index(drop=True)

    # COGS ~40-48% of revenue with slight random variation (typical for product+services mix)
    cogs_rate = rng.normal(0.44, 0.02, size=len(finance)).clip(0.35, 0.55)
    finance["cogs"] = (finance["revenue"] * cogs_rate).round(2)
    finance["gross_profit"] = (finance["revenue"] - finance["cogs"]).round(2)

    # Other opex: salaries/admin/rent, scales gently with revenue plus a fixed base
    finance["other_opex"] = (finance["revenue"] * 0.22 + rng.normal(15000, 2000, size=len(finance))).round(2)

    finance["operating_profit"] = (
        finance["gross_profit"] - finance["marketing_spend"] - finance["other_opex"]
    ).round(2)

    # Simple cash flow proxy: operating profit +/- working capital noise
    finance["cash_flow"] = (finance["operating_profit"] + rng.normal(0, 4000, size=len(finance))).round(2)

    finance["month"] = pd.to_datetime(finance["month"])

    # Drop any leading ramp-up month(s) where revenue is 0 due to the sales
    # and marketing date grids not perfectly aligning at the very start of
    # the window. Keeping these would show a misleading "loss-making" month
    # with no real sales activity behind it.
    finance = finance[finance["revenue"] > 0].reset_index(drop=True)

    # Drop the current, still-in-progress calendar month. "Today" falls
    # partway through its month, so that month only has a partial count of
    # transactions -- including it would make revenue look like it crashed
    # month-over-month when really the month just isn't finished yet.
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_month_start = pd.Timestamp(today.year, today.month, 1)
    finance = finance[finance["month"] < current_month_start].reset_index(drop=True)

    return finance


def current_month_start() -> pd.Timestamp:
    """Returns the first day of the current (still in-progress) calendar month.
    Shared by app.py so every monthly chart/aggregation excludes this partial
    month consistently -- see generate_finance_data for why this matters."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return pd.Timestamp(today.year, today.month, 1)


def generate_all_data(n_customers: int = 400, months_back: int = 24, seed: int = 42):
    """Convenience wrapper: generates and returns all linked datasets."""
    customers = generate_customers(n_customers=n_customers, seed=seed)
    sales = generate_sales_data(customers, months_back=months_back, seed=seed)
    marketing = generate_marketing_data(months_back=months_back, seed=seed)
    finance = generate_finance_data(sales, marketing, seed=seed)
    return customers, sales, marketing, finance


if __name__ == "__main__":
    # Quick standalone sanity check when run directly: python data_generator.py
    customers, sales, marketing, finance = generate_all_data()
    print("Customers:", customers.shape)
    print("Sales transactions:", sales.shape)
    print("Marketing rows:", marketing.shape)
    print("Finance rows:", finance.shape)
    print("\nSample sales:\n", sales.head())
    print("\nSample finance:\n", finance.head())
