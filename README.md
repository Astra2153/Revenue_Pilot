# RevenuePilot

**AI-powered Sales, Marketing & Finance Analytics Platform**

RevenuePilot is a full-stack analytics dashboard that unifies sales, marketing, and finance data into a single view, with machine-learning-driven revenue forecasting, RFM customer segmentation, and churn-risk scoring. It's built with Python, Streamlit, scikit-learn, Plotly, and Pandas.

This repository ships with a sample dataset modeled on Meridian Automation Solutions, a fictional B2B industrial automation and robotics solutions provider, so the platform can be explored end to end without needing a real company's data.

## Features

| Module | What it shows | How it's calculated |
|---|---|---|
| Sales | Revenue trends, a forward-looking forecast, and breakdowns by region, product category, and sales channel | `RandomForestRegressor` trained on lagged and seasonal features |
| Marketing | Spend, conversion funnel, CAC, and ROI by channel | Channel-level cost and ROI calculation from campaign data |
| Finance | Revenue, COGS, gross and operating margin, cash flow | A profit-and-loss rollup derived from the sales and marketing data |
| Customer Intelligence | RFM customer segments, churn-risk scores, and a list of high-value at-risk customers | `KMeans` clustering (RFM) and a `RandomForestClassifier` (churn) |

Every tab also surfaces a handful of plain-English insight statements, generated directly from the underlying numbers rather than from a language model.

## How it works

- **`data_generator.py`** builds a realistic, internally consistent dataset (sales transactions, marketing campaigns, monthly finance records, and a customer base), with seasonality and customer churn built in so the models have real patterns to learn from.
- **`analytics.py`** contains the machine learning: revenue forecasting, RFM-based customer segmentation, churn-risk scoring, marketing ROI calculations, and the logic behind the auto-generated insights.
- **`app.py`** is the Streamlit dashboard that ties everything together into four tabs.

No external AI API or language model is used anywhere in this project. All modeling is done with classical, well-understood scikit-learn algorithms, and every insight sentence is generated from a real, traceable calculation rather than free-form text generation.

## Tech stack

Python, Streamlit, scikit-learn, Plotly, Pandas

## Getting started

Requires Python 3.10, 3.11, or 3.12.

```bash
git clone https://github.com/<your-username>/RevenuePilot.git
cd RevenuePilot
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

This opens a local dashboard, usually at `http://localhost:8501`. The first load takes a few seconds while the sample data is generated and the models are trained; after that, switching tabs is instant.

To run the analytics pipeline on its own, without the dashboard:
```bash
python3 test_analytics.py
```
This runs the full pipeline in the terminal and prints `ALL CHECKS PASSED` if everything is working correctly.

## Using your own data

Swap in a real dataset by replacing the four DataFrames `app.py` loads via `load_data()`, matching these column names:

- **sales:** `customer_id, date, region, product_category, sales_channel, revenue, units_sold`
- **marketing:** `month, channel, spend, impressions, clicks, leads_generated, conversions`
- **finance:** `month, revenue, marketing_spend, cogs, gross_profit, other_opex, operating_profit, cash_flow`
- **customers:** `customer_id, segment, region, signup_date`

As long as the data matches this shape, no other code changes are required.

## Project structure

```
RevenuePilot/
├── app.py               Streamlit dashboard: all four tabs, charts, and UI
├── analytics.py          Machine learning: forecasting, segmentation, churn, ROI, insights
├── data_generator.py      Generates the underlying sales, marketing, and finance data
├── test_analytics.py      Runs the full pipeline from the terminal, without the dashboard
├── requirements.txt       Pinned, tested dependency versions
├── .gitignore
└── README.md
```

## Deployment

This app deploys for free on Streamlit Community Cloud:

1. Push a fork or clone of this repository to your own GitHub account.
2. Go to share.streamlit.io and sign in with GitHub.
3. Create a new app, point it at your repository, and set the main file to `app.py`.
4. Deploy. Streamlit installs `requirements.txt` and launches the app automatically.

## Limitations

- The revenue forecast is validated against a limited holdout set (roughly 24 months of data), so its error estimate should be read as directional rather than precise.
- Marketing ROI uses median customer lifetime value as a proxy for the value of a single conversion, since there is no direct link between an individual marketing conversion and a specific later sale. A production deployment with UTM or CRM-level tracking could attribute this more precisely.
- Churn risk is based on a simple rule (no purchase in 120+ days), not an observed cancellation event.

## Troubleshooting

| Problem | Fix |
|---|---|
| `streamlit: command not found` | Activate the virtual environment first, or run `python3 -m streamlit run app.py` |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again with the virtual environment active |
| Running `python app.py` directly does nothing | Streamlit apps must be launched with `streamlit run app.py`, not run as a plain Python script |
| `TypeError` mentioning `width` in a dataframe or chart call | A much newer Streamlit version is installed than the one this was tested with; run `pip install streamlit==1.38.0` |
| Charts appear blank | Check the terminal for errors, and try reducing the customer count in the sidebar |
| Port already in use | Run `streamlit run app.py --server.port 8502` (or any other free port) |

## Author

Ashmit Sanjay Katale
