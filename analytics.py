"""
analytics.py

Core analytics engine for RevenuePilot. Contains three ML components plus
an auto-insight generator that turns model output into plain-English
takeaways for the dashboard:

    1. RevenueForecaster   - RandomForestRegressor for monthly revenue forecasting
    2. CustomerSegmenter   - K-Means clustering on RFM (Recency/Frequency/Monetary) features
    3. ChurnScorer         - RandomForestClassifier-based churn-risk scoring
    4. AnomalyDetector     - IsolationForest-based outlier flagging (finance/marketing/sales)
    5. CohortAnalyzer      - Signup-month cohort retention analysis
    6. generate_insights   - Rule-based auto-insights across all modules

Kept framework-agnostic (no Streamlit imports) so it can be unit-tested or
reused outside the dashboard.

Author: Ashmit Sanjay Katale
"""

from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score


# ------------------------------------------------------------------
# 1. Revenue Forecasting  (RandomForestRegressor)
# ------------------------------------------------------------------
class RevenueForecaster:
    """
    Forecasts future monthly revenue using a RandomForestRegressor trained
    on time-based and lag features derived from historical finance data.
    """

    def __init__(self, n_estimators: int = 300, random_state: int = 42):
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=6,
            min_samples_leaf=2,
            random_state=random_state,
        )
        self.is_fitted = False
        self.feature_cols = ["month_index", "month_of_year", "lag_1", "lag_2", "lag_3", "rolling_mean_3"]
        self.metrics_ = {}

    @staticmethod
    def _build_features(finance_df: pd.DataFrame) -> pd.DataFrame:
        df = finance_df[["month", "revenue"]].copy().sort_values("month").reset_index(drop=True)
        df["month_index"] = np.arange(len(df))
        df["month_of_year"] = pd.to_datetime(df["month"]).dt.month
        df["lag_1"] = df["revenue"].shift(1)
        df["lag_2"] = df["revenue"].shift(2)
        df["lag_3"] = df["revenue"].shift(3)
        df["rolling_mean_3"] = df["revenue"].shift(1).rolling(window=3).mean()
        return df

    def fit(self, finance_df: pd.DataFrame):
        df = self._build_features(finance_df).dropna().reset_index(drop=True)

        X = df[self.feature_cols]
        y = df["revenue"]

        if len(df) >= 8:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.25, random_state=42, shuffle=False
            )
            self.model.fit(X_train, y_train)
            preds = self.model.predict(X_test)
            self.metrics_ = {
                "mae": float(mean_absolute_error(y_test, preds)),
                "r2": float(r2_score(y_test, preds)) if len(y_test) > 1 else None,
                "test_size": len(y_test),
            }
            # refit on full data for best final forecasts
            self.model.fit(X, y)
        else:
            self.model.fit(X, y)
            self.metrics_ = {"mae": None, "r2": None, "test_size": 0}

        self._last_rows = df.tail(3).copy()
        self._last_month_index = int(df["month_index"].iloc[-1])
        self._last_month_date = pd.to_datetime(finance_df["month"]).max()
        self.is_fitted = True
        return self

    def forecast(self, periods: int = 6) -> pd.DataFrame:
        """Recursively forecasts `periods` months ahead."""
        if not self.is_fitted:
            raise RuntimeError("Call .fit() before .forecast().")

        history = list(self._last_rows["revenue"].values)
        results = []
        current_index = self._last_month_index
        current_date = self._last_month_date

        for _ in range(periods):
            current_index += 1
            current_date = (current_date + pd.DateOffset(months=1))

            lag_1 = history[-1]
            lag_2 = history[-2] if len(history) >= 2 else lag_1
            lag_3 = history[-3] if len(history) >= 3 else lag_2
            rolling_mean_3 = np.mean(history[-3:])

            row = pd.DataFrame([{
                "month_index": current_index,
                "month_of_year": current_date.month,
                "lag_1": lag_1,
                "lag_2": lag_2,
                "lag_3": lag_3,
                "rolling_mean_3": rolling_mean_3,
            }])[self.feature_cols]

            pred = float(self.model.predict(row)[0])
            pred = max(0, pred)
            results.append({"month": current_date, "forecast_revenue": pred})
            history.append(pred)

        return pd.DataFrame(results)

    def feature_importances(self) -> pd.DataFrame:
        if not self.is_fitted:
            return pd.DataFrame()
        return pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------
# 2. Customer Segmentation (K-Means on RFM features)
# ------------------------------------------------------------------
class CustomerSegmenter:
    """
    Computes RFM (Recency, Frequency, Monetary) features per customer and
    clusters them with K-Means into actionable segments (e.g. Champions,
    Loyal, At Risk, Lost, New/Low-Value), labeled by relative RFM ranking
    rather than fixed cluster IDs so labels stay meaningful across refits.
    """

    def __init__(self, n_clusters: int = 4, random_state: int = 42):
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        self.is_fitted = False

    @staticmethod
    def compute_rfm(sales_df: pd.DataFrame, reference_date: datetime = None) -> pd.DataFrame:
        if reference_date is None:
            reference_date = pd.to_datetime(sales_df["date"]).max() + pd.Timedelta(days=1)

        grouped = sales_df.groupby("customer_id").agg(
            last_purchase=("date", "max"),
            frequency=("transaction_id", "count"),
            monetary=("revenue", "sum"),
        ).reset_index()

        grouped["recency_days"] = (pd.to_datetime(reference_date) - pd.to_datetime(grouped["last_purchase"])).dt.days
        return grouped

    def fit_predict(self, sales_df: pd.DataFrame, customers_df: pd.DataFrame = None) -> pd.DataFrame:
        rfm = self.compute_rfm(sales_df)

        X = rfm[["recency_days", "frequency", "monetary"]].copy()
        # log-transform monetary/frequency to reduce skew from big-spend outliers
        X["monetary"] = np.log1p(X["monetary"])
        X["frequency"] = np.log1p(X["frequency"])

        X_scaled = self.scaler.fit_transform(X)
        cluster_labels = self.model.fit_predict(X_scaled)
        rfm["cluster"] = cluster_labels
        self.is_fitted = True

        # Rank clusters by a composite "value score" so labels are meaningful:
        # low recency (recent) + high frequency + high monetary = best segment
        cluster_profile = rfm.groupby("cluster").agg(
            avg_recency=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
        )
        cluster_profile["value_score"] = (
            cluster_profile["avg_monetary"].rank() +
            cluster_profile["avg_frequency"].rank() -
            cluster_profile["avg_recency"].rank()
        )
        ranked_clusters = cluster_profile.sort_values("value_score", ascending=False).index.tolist()

        n = len(ranked_clusters)
        label_bank = ["Champions", "Loyal Customers", "At Risk", "Lost / Dormant", "New / Low-Value"]
        labels_for_rank = (label_bank + [f"Segment {i}" for i in range(n)])[:n]
        cluster_to_label = {cluster: labels_for_rank[i] for i, cluster in enumerate(ranked_clusters)}

        rfm["segment_label"] = rfm["cluster"].map(cluster_to_label)

        if customers_df is not None:
            rfm = rfm.merge(customers_df[["customer_id", "segment", "region"]], on="customer_id", how="left")

        return rfm

    def segment_summary(self, rfm_result: pd.DataFrame) -> pd.DataFrame:
        summary = rfm_result.groupby("segment_label").agg(
            customers=("customer_id", "count"),
            avg_recency_days=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
            total_monetary=("monetary", "sum"),
        ).sort_values("total_monetary", ascending=False).reset_index()
        return summary.round(1)


# ------------------------------------------------------------------
# 3. Churn Risk Scoring (RandomForestClassifier)
# ------------------------------------------------------------------
class ChurnScorer:
    """
    Trains a RandomForestClassifier to estimate churn probability per
    customer, using RFM-derived behavioral features. Churn label is
    defined heuristically (no purchase in the last N days relative to
    that customer's typical cadence) since this is a synthetic dataset
    with no ground-truth churn flag -- documented clearly for transparency.
    """

    def __init__(self, n_estimators: int = 300, random_state: int = 42, churn_recency_threshold_days: int = 120):
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=5,
            min_samples_leaf=3,
            random_state=random_state,
            class_weight="balanced",
        )
        self.random_state = random_state
        self.churn_recency_threshold_days = churn_recency_threshold_days
        self.is_fitted = False
        self.feature_cols = ["recency_days", "frequency", "monetary", "avg_order_value"]
        self.metrics_ = {}

    def _prepare_features(self, rfm: pd.DataFrame) -> pd.DataFrame:
        df = rfm.copy()
        df["avg_order_value"] = df["monetary"] / df["frequency"].replace(0, 1)
        df["churned"] = (df["recency_days"] > self.churn_recency_threshold_days).astype(int)
        return df

    def fit_predict(self, rfm: pd.DataFrame) -> pd.DataFrame:
        df = self._prepare_features(rfm)
        X = df[self.feature_cols]
        y = df["churned"]

        if y.nunique() < 2 or len(df) < 20:
            # Not enough class diversity/data to train meaningfully; fall back
            # to a transparent rule-based risk score instead of a fitted model.
            df["churn_probability"] = (df["recency_days"] / df["recency_days"].max()).clip(0, 1)
            self.metrics_ = {"accuracy": None, "note": "rule-based fallback (insufficient data/class balance)"}
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.25, random_state=self.random_state, stratify=y
            )
            self.model.fit(X_train, y_train)
            preds = self.model.predict(X_test)
            accuracy = float((preds == y_test).mean())
            self.metrics_ = {"accuracy": accuracy, "test_size": len(y_test)}

            # refit on all data for the best final scores shown in the dashboard
            self.model.fit(X, y)
            df["churn_probability"] = self.model.predict_proba(X)[:, 1]

        def risk_bucket(p):
            if p >= 0.66:
                return "High Risk"
            elif p >= 0.33:
                return "Medium Risk"
            return "Low Risk"

        df["churn_risk"] = df["churn_probability"].apply(risk_bucket)
        self.is_fitted = True
        return df

    def feature_importances(self) -> pd.DataFrame:
        if not self.is_fitted or not hasattr(self.model, "feature_importances_"):
            return pd.DataFrame()
        return pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------
# 4. Marketing ROI helper
# ------------------------------------------------------------------
def compute_marketing_roi(marketing_df: pd.DataFrame, avg_customer_value: float) -> pd.DataFrame:
    """
    Computes CAC (cost per conversion) and an approximate ROI multiple per
    channel: (conversions * avg_customer_value - spend) / spend.

    NOTE on avg_customer_value: pass the MEDIAN customer lifetime value
    (not the mean) from the RFM table. A small number of high-spend
    Enterprise "whale" accounts skews the mean far above what a typical
    newly-converted customer is worth, which would overstate ROI for
    every channel. The median is a more honest stand-in for "value of a
    typical new conversion" given this dataset has no per-conversion
    revenue attribution back to an individual customer.
    """
    channel_summary = marketing_df.groupby("channel").agg(
        total_spend=("spend", "sum"),
        total_leads=("leads_generated", "sum"),
        total_conversions=("conversions", "sum"),
    ).reset_index()

    channel_summary["cac"] = (channel_summary["total_spend"] / channel_summary["total_conversions"].replace(0, np.nan)).round(2)
    channel_summary["estimated_value_generated"] = (channel_summary["total_conversions"] * avg_customer_value).round(2)
    channel_summary["roi_multiple"] = (
        (channel_summary["estimated_value_generated"] - channel_summary["total_spend"])
        / channel_summary["total_spend"]
    ).round(2)
    channel_summary["conversion_rate"] = (
        channel_summary["total_conversions"] / channel_summary["total_leads"].replace(0, np.nan)
    ).round(3)

    return channel_summary.sort_values("roi_multiple", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------
# 5. Anomaly Detection (IsolationForest)
# ------------------------------------------------------------------
class AnomalyDetector:
    """
    Flags statistically unusual data points using IsolationForest across
    three grains: monthly finance records, monthly marketing channel
    performance, and individual sales transactions.

    This is a FLAGGING tool, not a diagnosis -- each returned row gets an
    anomaly_score (higher = more unusual) and an is_anomaly boolean, so the
    caller (API/dashboard) decides how to surface it. `contamination`
    controls the expected proportion of anomalies (default 8%, i.e.
    roughly the most unusual 1-in-12 rows get flagged).
    """

    def __init__(self, contamination: float = 0.08, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state

    def _fit_flag(self, X: pd.DataFrame, min_rows: int = 6):
        """Shared IsolationForest fit/score helper; too few rows to fit
        meaningfully just returns "nothing flagged" rather than a noisy
        model fit on a handful of points."""
        if len(X) < min_rows:
            return np.ones(len(X), dtype=int), np.zeros(len(X))
        model = IsolationForest(contamination=self.contamination, random_state=self.random_state)
        preds = model.fit_predict(X)
        scores = (-model.decision_function(X)).round(4)  # flip sign: higher score = more anomalous
        return preds, scores

    def detect_finance(self, finance_df: pd.DataFrame) -> pd.DataFrame:
        """Flags unusual months across the full P&L shape (revenue, cogs,
        opex, cash flow, etc.) -- e.g. a month where cash flow diverged
        sharply from operating profit, or costs spiked independent of
        revenue."""
        feature_cols = [
            "revenue", "cogs", "gross_profit", "marketing_spend",
            "other_opex", "operating_profit", "cash_flow",
        ]
        df = finance_df.copy().sort_values("month").reset_index(drop=True)
        X = df[feature_cols].fillna(0)

        preds, scores = self._fit_flag(X)
        df["anomaly_score"] = scores
        df["is_anomaly"] = preds == -1
        return df.sort_values("anomaly_score", ascending=False).reset_index(drop=True)

    def detect_marketing(self, marketing_df: pd.DataFrame) -> pd.DataFrame:
        """Flags unusual channel-months -- e.g. a sudden CAC spike or a
        conversion-rate collapse for one channel in one month. Fit PER
        CHANNEL, since baseline CAC/CTR differ hugely by channel type
        (Trade Shows vs. Referral Program) -- a single pooled model would
        just rediscover "which channel is this" instead of real anomalies."""
        df = marketing_df.copy()
        df["cac"] = df["spend"] / df["conversions"].replace(0, np.nan)
        df["ctr"] = df["clicks"] / df["impressions"].replace(0, np.nan)
        df["conversion_rate"] = df["conversions"] / df["leads_generated"].replace(0, np.nan)
        feature_cols = ["spend", "cac", "ctr", "conversion_rate"]

        results = []
        for channel, group in df.groupby("channel"):
            group = group.copy()
            X = group[feature_cols].fillna(group[feature_cols].mean()).fillna(0)
            preds, scores = self._fit_flag(X)
            group["anomaly_score"] = scores
            group["is_anomaly"] = preds == -1
            results.append(group)

        out = pd.concat(results, ignore_index=True)
        return out.sort_values("anomaly_score", ascending=False).reset_index(drop=True)

    def detect_sales(self, sales_df: pd.DataFrame, customers_df: pd.DataFrame = None, top_n: int = 100) -> pd.DataFrame:
        """Flags unusual individual transactions. Fit PER CUSTOMER SEGMENT
        (merging in customers_df the same way CustomerSegmenter does) since
        a $12,000 order is routine for an Enterprise account but would be
        wildly unusual for an SMB one -- pooling all segments together
        would just flag every Enterprise transaction as "anomalous"."""
        df = sales_df.copy()
        has_segment = "segment" in df.columns and df["segment"].notna().any()
        if not has_segment and customers_df is not None:
            df = df.drop(columns=[c for c in ["segment"] if c in df.columns])
            df = df.merge(customers_df[["customer_id", "segment"]], on="customer_id", how="left")
            has_segment = df["segment"].notna().any()

        group_col = "segment" if has_segment else "product_category"
        feature_cols = ["revenue", "units_sold"]

        results = []
        for key, group in df.groupby(group_col):
            group = group.copy()
            X = group[feature_cols].fillna(0)
            preds, scores = self._fit_flag(X, min_rows=10)
            group["anomaly_score"] = scores
            group["is_anomaly"] = preds == -1
            results.append(group)

        out = pd.concat(results, ignore_index=True).sort_values("anomaly_score", ascending=False).reset_index(drop=True)
        return out.head(top_n) if top_n else out


# ------------------------------------------------------------------
# 6. Cohort Retention Analysis
# ------------------------------------------------------------------
class CohortAnalyzer:
    """
    Groups customers into cohorts by SIGNUP MONTH and tracks what
    percentage of each cohort is still purchasing N months later.

    Complements RFM/churn: those give a point-in-time snapshot per
    customer, while this shows retention as a TREND over calendar time --
    e.g. whether cohorts that signed up more recently retain better or
    worse than older ones, which a single churn score can't reveal.
    """

    def build_cohort_table(self, sales_df: pd.DataFrame, customers_df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns a long-format table: one row per (cohort_month, period_number)
        with active_customers, cohort_size, and retention_rate. period_number
        is the number of whole months since that cohort's signup month
        (0 = signup month itself, 1 = one month later, etc.).
        """
        cust = customers_df.copy()
        cust["cohort_month"] = pd.to_datetime(cust["signup_date"]).values.astype("datetime64[M]")

        sales = sales_df.copy()
        sales["activity_month"] = pd.to_datetime(sales["date"]).values.astype("datetime64[M]")

        merged = sales.merge(cust[["customer_id", "cohort_month"]], on="customer_id", how="inner")
        merged["cohort_month"] = pd.to_datetime(merged["cohort_month"])
        merged["activity_month"] = pd.to_datetime(merged["activity_month"])

        merged["period_number"] = (
            (merged["activity_month"].dt.year - merged["cohort_month"].dt.year) * 12
            + (merged["activity_month"].dt.month - merged["cohort_month"].dt.month)
        )
        merged = merged[merged["period_number"] >= 0]  # safety: drop any pre-signup edge cases

        cohort_sizes = cust.groupby("cohort_month")["customer_id"].nunique().rename("cohort_size")

        active = (
            merged.groupby(["cohort_month", "period_number"])["customer_id"]
            .nunique()
            .rename("active_customers")
            .reset_index()
        )

        table = active.merge(cohort_sizes, on="cohort_month", how="left")
        table["retention_rate"] = (table["active_customers"] / table["cohort_size"]).round(4)

        return table.sort_values(["cohort_month", "period_number"]).reset_index(drop=True)

    def retention_matrix(self, cohort_table: pd.DataFrame) -> pd.DataFrame:
        """
        Pivots the long table into a wide cohort x period matrix of
        retention rates -- the classic "cohort heatmap" shape used for
        SaaS/B2B retention charts. Rows = cohort_month, columns =
        period_number (months since signup), values = retention_rate.
        """
        matrix = cohort_table.pivot(index="cohort_month", columns="period_number", values="retention_rate")
        return matrix.sort_index()


# ------------------------------------------------------------------
# 7. Auto-generated, data-driven insights (rule-based NLG)
# ------------------------------------------------------------------
def generate_insights(sales_df, marketing_df, finance_df, rfm_result, churn_result, roi_summary, forecast_df) -> dict:
    """
    Produces short, plain-English, data-driven insight bullets for each
    dashboard module. Every sentence is generated from an actual computed
    number (no hard-coded text) so insights update as data changes.
    """
    insights = {"sales": [], "marketing": [], "finance": [], "customer": []}

    # --- Sales insights ---
    # Use the finance table's monthly revenue (already excludes the current,
    # still-in-progress month) rather than recomputing from raw sales_df, so
    # month-over-month comparisons never compare a full month to a partial one.
    monthly_rev = finance_df.set_index("month")["revenue"].sort_index()

    if len(monthly_rev) >= 2:
        mom_change = (monthly_rev.iloc[-1] - monthly_rev.iloc[-2]) / monthly_rev.iloc[-2] * 100
        direction = "up" if mom_change >= 0 else "down"
        insights["sales"].append(
            f"Revenue is {direction} {abs(mom_change):.1f}% month-over-month, "
            f"reaching ${monthly_rev.iloc[-1]:,.0f} in the most recent month."
        )

    top_region = sales_df.groupby("region")["revenue"].sum().idxmax()
    top_region_share = sales_df.groupby("region")["revenue"].sum().max() / sales_df["revenue"].sum() * 100
    insights["sales"].append(f"{top_region} is the top-performing region, contributing {top_region_share:.1f}% of total revenue.")

    top_category = sales_df.groupby("product_category")["revenue"].sum().idxmax()
    insights["sales"].append(f"{top_category} is the best-selling product category by total revenue.")

    if not forecast_df.empty:
        forecast_growth = (forecast_df["forecast_revenue"].iloc[-1] - monthly_rev.iloc[-1]) / monthly_rev.iloc[-1] * 100
        trend_word = "growth" if forecast_growth >= 0 else "decline"
        insights["sales"].append(
            f"The forecasting model projects {abs(forecast_growth):.1f}% revenue {trend_word} over the next "
            f"{len(forecast_df)} months."
        )

    # --- Marketing insights ---
    best_channel = roi_summary.iloc[0]
    insights["marketing"].append(
        f"{best_channel['channel']} delivers the strongest ROI at {best_channel['roi_multiple']:.1f}x, "
        f"with an estimated CAC of ${best_channel['cac']:,.0f} per conversion."
    )

    worst_channel = roi_summary.sort_values("roi_multiple").iloc[0]
    if worst_channel["roi_multiple"] < 0.5:
        insights["marketing"].append(
            f"{worst_channel['channel']} shows the weakest ROI ({worst_channel['roi_multiple']:.1f}x) "
            f"and may warrant a reduced budget allocation."
        )

    total_conversions = int(roi_summary["total_conversions"].sum())
    total_spend = roi_summary["total_spend"].sum()
    insights["marketing"].append(
        f"Across all channels, ${total_spend:,.0f} in spend generated {total_conversions:,} new customer conversions."
    )

    # --- Finance insights ---
    latest = finance_df.sort_values("month").iloc[-1]
    gross_margin = latest["gross_profit"] / latest["revenue"] * 100 if latest["revenue"] else 0
    insights["finance"].append(f"Latest gross margin stands at {gross_margin:.1f}%, on ${latest['revenue']:,.0f} in monthly revenue.")

    op_margin = latest["operating_profit"] / latest["revenue"] * 100 if latest["revenue"] else 0
    profitability = "profitable" if latest["operating_profit"] >= 0 else "operating at a loss"
    insights["finance"].append(f"The business is currently {profitability}, with an operating margin of {op_margin:.1f}%.")

    avg_cash_flow = finance_df["cash_flow"].tail(6).mean()
    insights["finance"].append(f"Average cash flow over the trailing 6 months is ${avg_cash_flow:,.0f} per month.")

    # --- Customer intelligence insights ---
    seg_summary = rfm_result["segment_label"].value_counts(normalize=True) * 100
    top_segment = seg_summary.idxmax()
    insights["customer"].append(f"{top_segment} is the largest customer segment, representing {seg_summary.max():.1f}% of the customer base.")

    high_risk_pct = (churn_result["churn_risk"] == "High Risk").mean() * 100
    insights["customer"].append(f"{high_risk_pct:.1f}% of customers are currently flagged as High Risk for churn.")

    high_risk_value = churn_result.loc[churn_result["churn_risk"] == "High Risk", "monetary"].sum()
    insights["customer"].append(f"High-risk customers represent ${high_risk_value:,.0f} in historical revenue that could be at stake without retention action.")

    return insights
