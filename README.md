# RevenuePilot

**A full-stack sales, marketing, finance, and HR-analytics platform for a fictional B2B automation company — with an AI layer that's built to admit what it doesn't know.**

🔗 **Live app:** https://revenue-pilot-6kax.vercel.app
🔗 **API docs:** https://revenue-pilot-s19u.onrender.com/docs

> The backend is on a free tier and sleeps after inactivity — the first request can take ~30-60 seconds to wake it up. That's normal, not a bug.

---

## What this actually is

Most portfolio dashboards stop at "here's a chart." This one goes further in three specific ways:

1. **A natural-language-to-SQL engine with a real security layer.** Ask a question in plain English; an LLM writes SQL; before that SQL ever touches the database it passes through a deterministic validator (read-only enforcement, table allow-lists per division, forbidden-schema blocking, row-limit injection) — tested against 30 adversarial attack cases, all passing. The model never gets to decide what it's allowed to touch.

2. **An employee performance scoring system that was built to catch its own bias — and did.** Naive "who closed the most deals" rankings punish anyone working harder, larger accounts. This system weights performance by how genuinely difficult each account segment is to close, computed from the data itself rather than a hardcoded opinion. While building it, three separate real bugs surfaced and were fixed in sequence: the difficulty weighting could overcorrect on small samples, the fix for that was still confounded by deal *size*, and the fix for *that* was still confounded by deal *volume*. The final system also runs a statistical fairness audit that honestly reports when it doesn't have enough data to judge, rather than forcing a verdict.

3. **A live, deployed, end-to-end product**, not a script that runs on one machine. Real backend on Render, real frontend on Vercel, real Postgres on Supabase, actually reachable by anyone with the link.

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Revenue trend, marketing channel returns, and auto-generated plain-English insights |
| **Finance** | Revenue/cost breakdown, margin trends, cash flow, full monthly ledger |
| **Customer Intelligence** | RFM customer segmentation (K-Means), churn-risk scoring (Random Forest), at-risk revenue |
| **Marketing Funnel** | Spend, leads, conversions, CAC and ROI by channel |
| **CRM** | Deal leaderboard — raw performance next to difficulty-adjusted performance, side by side, plus a fairness audit |
| **Admin** | Employee management, gated by a passkey checked server-side, with an access log and a performance chart |
| **Scenario Simulator** | Live what-if modeling: re-runs the real forecasting model at different horizons, plus a churn-retention calculator |
| **Chatbot** | Two modes: conversational Q&A grounded in precomputed summaries, and the NL-to-SQL query engine described above |
| **Audit Log** | Every insert/update/delete across employees and CRM data, with before/after diffs |
| **Reports** | Preview and send an AI-written monthly report (causal "why did this happen" reasoning, not just "what happened") |

## Architecture

```
React + TypeScript + Vite + Tailwind + shadcn/ui   (Vercel)
              │  REST
FastAPI (Python)                                    (Render)
              │
Supabase (Postgres)
              │
Google Gemini API  (chat, causal reasoning, NL-to-SQL, report narratives)
Resend             (email delivery)
```

**Why this split:** FastAPI needs a persistent server process, which Vercel's serverless model doesn't suit — so the backend lives on Render while Vercel serves the frontend. They're connected by one environment variable (`VITE_API_BASE_URL`), not by being in the same deployment.

## Tech stack

**Backend:** Python, FastAPI, Supabase (Postgres), pandas, scikit-learn (RandomForest for forecasting and churn, K-Means for segmentation), Google Gemini API, Resend
**Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts, React Router

## Machine learning, specifically

- **Revenue forecasting** — `RandomForestRegressor` on lagged + seasonal features, validated on a holdout set
- **Customer segmentation** — K-Means clustering on Recency/Frequency/Monetary (RFM) values
- **Churn scoring** — `RandomForestClassifier`, with feature importances surfaced in the UI, not hidden
- **Employee performance normalization** — a from-scratch statistical model (not a library): difficulty weights derived from each segment's real win rate, shrunk toward the overall mean to resist small-sample noise, capped to prevent runaway compounding, and expressed as a scale-invariant per-deal index so a rep working 6 huge deals can be compared fairly against a rep working 60 small ones

## Known limitations

Stated plainly rather than glossed over:

- **Authentication is minimal.** The Admin Portal is gated by a single shared passkey checked server-side — genuine protection against casual access, but it identifies *a browser that knew the passkey*, not *a specific person*. Per-user login is the natural next step.
- **Email delivery is capped by Resend's free tier**, which only delivers to the account's one verified address. The report-generation and formatting logic is fully real; only actual inbox delivery to arbitrary recipients needs a verified sending domain.
- **CORS is currently open (`*`)** for ease of development; would be scoped to the specific frontend origin before any real production use.
- **All data is synthetic**, generated with realistic seasonality, churn, and segment patterns — there is no real company behind this.

## Running it locally

Needs Python 3.11+, Node 18+, and your own Supabase project + API keys (Gemini, Resend).

```bash
git clone https://github.com/Astra2153/Revenue_Pilot.git
cd Revenue_Pilot

# Backend
pip install -r requirements.txt
# create a .env with SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY,
# GEMINI_API_KEY, RESEND_API_KEY, ADMIN_PASSKEY
python -m uvicorn api.api:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
# create frontend/.env with VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Then run the schema and seed scripts against your own Supabase project (`revenuepilot_schema.sql`, then `api/seed_data.py`, `api/seed_org.py`, `api/seed_crm.py`, in that order) before the dashboard has anything to show.

## Author

Ashmit Sanjay Katale
