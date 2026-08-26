"""
Standalone validation script -- NOT part of the shipped app.
Runs the full data + analytics pipeline once and prints results so we can
verify everything works before wiring it into the Streamlit UI.
"""
from data_generator import generate_all_data
from analytics import RevenueForecaster, CustomerSegmenter, ChurnScorer, compute_marketing_roi, generate_insights

print("=" * 70)
print("STEP 1: Generating data")
print("=" * 70)
customers, sales, marketing, finance = generate_all_data()
print(f"Customers: {customers.shape} | Sales: {sales.shape} | Marketing: {marketing.shape} | Finance: {finance.shape}")

print("\n" + "=" * 70)
print("STEP 2: Revenue Forecasting (RandomForestRegressor)")
print("=" * 70)
forecaster = RevenueForecaster()
forecaster.fit(finance)
print("Metrics:", forecaster.metrics_)
forecast = forecaster.forecast(periods=6)
print(forecast)
print("\nFeature importances:")
print(forecaster.feature_importances())

print("\n" + "=" * 70)
print("STEP 3: Customer Segmentation (K-Means RFM)")
print("=" * 70)
segmenter = CustomerSegmenter(n_clusters=4)
rfm_result = segmenter.fit_predict(sales, customers)
print(rfm_result.head())
print("\nSegment summary:")
seg_summary = segmenter.segment_summary(rfm_result)
print(seg_summary)
assert rfm_result["customer_id"].nunique() == len(rfm_result), "Duplicate customers in RFM result!"

print("\n" + "=" * 70)
print("STEP 4: Churn Risk Scoring (RandomForestClassifier)")
print("=" * 70)
churn_scorer = ChurnScorer()
churn_result = churn_scorer.fit_predict(rfm_result)
print("Metrics:", churn_scorer.metrics_)
print(churn_result[["customer_id", "recency_days", "frequency", "monetary", "churn_probability", "churn_risk"]].head(10))
print("\nChurn risk distribution:")
print(churn_result["churn_risk"].value_counts())
print("\nFeature importances:")
print(churn_scorer.feature_importances())

print("\n" + "=" * 70)
print("STEP 5: Marketing ROI")
print("=" * 70)
avg_customer_value = rfm_result["monetary"].median()
roi_summary = compute_marketing_roi(marketing, avg_customer_value)
print(roi_summary)

print("\n" + "=" * 70)
print("STEP 6: Auto-generated insights")
print("=" * 70)
insights = generate_insights(sales, marketing, finance, rfm_result, churn_result, roi_summary, forecast)
for module, bullets in insights.items():
    print(f"\n[{module.upper()}]")
    for b in bullets:
        print(" -", b)

print("\n" + "=" * 70)
print("ALL CHECKS PASSED")
print("=" * 70)
