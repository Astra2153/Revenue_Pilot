"""
kpi.py

Two things live here:

  1. Company-wide CEO scorecard -- a consolidated view across finance, sales,
     marketing, customer intelligence, and now the CRM/employee layer.

  2. Employee performance scoring -- DESIGNED TO RESIST THE OBVIOUS FAILURE
     MODE of this kind of feature: ranking people by raw deal count or win
     rate, which unfairly punishes anyone working harder/larger accounts.

=====================================================================
WHY THE SCORING WORKS THE WAY IT DOES
=====================================================================
Difficulty weighting is DATA-DRIVEN, not a hardcoded opinion about which
segment is "hard". We compute each segment's actual company-wide win rate
and weight a win by how rare a win in that segment actually is:

    difficulty_weight[segment] = overall_win_rate / segment_win_rate

A segment that converts at HALF the overall rate gets 2x credit per won
dollar; a segment that converts easily gets a weight below 1. This is
defensible under scrutiny in a way "we decided Enterprise is worth 3x" is
not -- it's derived from what the data actually shows about difficulty, and
it updates automatically as the business's own numbers change.

Both RAW and NORMALIZED metrics are always returned together. Hiding the raw
numbers behind only an adjusted score is itself a fairness problem -- a
manager needs to see both to trust either.

The narrative generator is instructed to cite only the numbers given to it
and to say "insufficient data" rather than speculate about effort, attitude,
or character -- see chatbot.py / report.py for the same discipline applied
to financial causal reasoning. Guessing at a PERSON's motivation from
secondhand numbers is a worse failure than guessing at why revenue moved.

run_fairness_audit() is a deterministic statistical check (no LLM), because
whether the scoring system itself still shows a systematic gap across
segment-focus groups after normalization is a factual question with a
factual answer -- not something to ask a language model to judge.
"""

import pandas as pd
import numpy as np
from google.genai import types

import chatbot
import db
import report  # reuses gather_monthly_report_data() for the company-wide financial/sales/marketing/customer blocks

MIN_DEALS_FOR_NARRATIVE = 3  # below this, there isn't enough signal to say anything meaningful


# ------------------------------------------------------------------
# 1. Company-wide CEO scorecard
# ------------------------------------------------------------------
def gather_company_kpis(bundle: dict) -> dict:
    """
    One consolidated scorecard: the existing finance/sales/marketing/customer
    blocks (same as the monthly report) plus company-wide CRM/employee stats.
    """
    base = report.gather_monthly_report_data(bundle)

    all_deals = db.get_crm_deals()
    all_employees = db.get_all_employees()

    if all_deals.empty:
        crm_block = {"note": "No CRM deal data found -- run api/seed_crm.py first."}
    else:
        closed = all_deals[all_deals["stage"].isin(["won", "lost"])]
        won = all_deals[all_deals["stage"] == "won"]
        crm_block = {
            "total_deals": int(len(all_deals)),
            "open_deals": int((~all_deals["stage"].isin(["won", "lost"])).sum()),
            "closed_deals": int(len(closed)),
            "won_deals": int(len(won)),
            "win_rate_pct": round(len(won) / len(closed) * 100, 1) if len(closed) else None,
            "total_won_value": float(won["value"].sum()) if not won.empty else 0.0,
            "avg_deal_value_won": float(won["value"].mean()) if not won.empty else None,
            "active_sales_employees": int(all_employees[all_employees["department"] == "Sales"].shape[0]) if not all_employees.empty else 0,
        }

    return {**base, "crm": crm_block}


# ------------------------------------------------------------------
# 2. Segment difficulty weights -- data-driven, not hardcoded
# ------------------------------------------------------------------
def compute_segment_avg_deal_values(all_deals: pd.DataFrame) -> dict:
    """
    Average deal VALUE per segment, across all deals company-wide (won, lost,
    and open -- the size of a typical deal, not just successful ones). Used
    to convert an employee's dollar contribution into a scale-invariant unit
    (see compute_employee_metrics' relative_contribution_index): a segment's
    deals being structurally 10-20x larger than another's is a real fact
    about deal size, not a difficulty or fairness question, and must not be
    conflated with the win-probability weighting below.
    """
    if all_deals.empty:
        return {}
    return {seg: float(group["value"].mean()) for seg, group in all_deals.groupby("segment")}


def compute_segment_difficulty_weights(all_deals: pd.DataFrame, shrinkage_k: int = 10, max_weight: float = 3.0, min_weight: float = 0.33) -> dict:
    """
    weight[segment] = overall_win_rate / shrunk_segment_win_rate

    Two corrections on top of the raw ratio, both necessary in practice (see
    the module docstring's note on overcorrection):

    1. SHRINKAGE. A segment with few closed deals produces a noisy win-rate
       estimate -- e.g. 2 wins out of 6 deals looks identical, statistically,
       to a coin flip. We blend the segment's observed win rate toward the
       overall win rate, weighted by shrinkage_k (a "how many deals' worth of
       trust does the overall rate get" prior strength). More deals in that
       segment -> the shrinkage matters less; few deals -> pulled toward the
       company-wide average instead of trusting a noisy small sample.

           shrunk_rate = (wins + k * overall_rate) / (closed + k)

    2. CAPPING. Multiplying a difficulty weight against an already-large
       dollar value can compound two skewed numbers into an extreme result.
       Capping the weight to [min_weight, max_weight] keeps a single noisy
       segment from dominating the leaderboard regardless of how the
       shrinkage estimate lands.

    Without both corrections, a small, high-value segment (fewer customers,
    bigger deals -- e.g. Enterprise) can swing from "looks unfairly punished"
    to "looks unfairly inflated" on nothing more than sampling noise. This
    was caught by run_fairness_audit() flagging an overcorrection in testing,
    not assumed in advance -- see that function's interpretation logic, which
    is direction-aware for exactly this reason.
    """
    closed = all_deals[all_deals["stage"].isin(["won", "lost"])]
    if closed.empty:
        return {}

    overall_win_rate = (closed["stage"] == "won").mean()
    weights = {}
    for segment, group in closed.groupby("segment"):
        n_closed = len(group)
        n_won = (group["stage"] == "won").sum()
        shrunk_rate = (n_won + shrinkage_k * overall_win_rate) / (n_closed + shrinkage_k)
        raw_weight = overall_win_rate / shrunk_rate if shrunk_rate > 0 else max_weight
        weights[segment] = round(min(max(raw_weight, min_weight), max_weight), 3)
    return weights


# ------------------------------------------------------------------
# 3. Per-employee raw + normalized metrics
# ------------------------------------------------------------------
def compute_employee_metrics(employee_id: str, all_deals: pd.DataFrame, all_activities: pd.DataFrame, difficulty_weights: dict, segment_avg_values: dict = None) -> dict:
    """
    Returns RAW metrics (what a naive dashboard would show) and NORMALIZED
    metrics (difficulty-adjusted) side by side -- never one without the
    other. Includes both an ABSOLUTE-dollar figure (legitimate for revenue
    reporting -- a CEO genuinely cares how many real dollars someone closed)
    and a scale-invariant "relative_contribution_index" (for FAIRNESS
    comparisons across segments with structurally different deal sizes --
    see compute_segment_avg_deal_values' docstring for why these must be
    kept separate).
    """
    segment_avg_values = segment_avg_values or {}
    deals = all_deals[all_deals["owner_employee_id"] == employee_id]
    activities = all_activities[all_activities["employee_id"] == employee_id] if not all_activities.empty else pd.DataFrame()

    if deals.empty:
        return {
            "employee_id": employee_id,
            "raw": {"total_deals": 0, "won_deals": 0, "win_rate_pct": None, "total_won_value": 0.0},
            "normalized": {"difficulty_adjusted_value": 0.0, "value_per_deal_worked": 0.0, "relative_contribution_index": 0.0},
            "activity_count": int(len(activities)),
            "sufficient_data": False,
        }

    closed = deals[deals["stage"].isin(["won", "lost"])]
    won = deals[deals["stage"] == "won"]

    raw = {
        "total_deals": int(len(deals)),
        "closed_deals": int(len(closed)),
        "won_deals": int(len(won)),
        "win_rate_pct": round(len(won) / len(closed) * 100, 1) if len(closed) else None,
        "total_won_value": float(won["value"].sum()) if not won.empty else 0.0,
        "avg_deal_value_won": float(won["value"].mean()) if not won.empty else None,
        "segment_mix": deals["segment"].value_counts().to_dict(),
    }

    # ABSOLUTE metric: each won dollar weighted by how hard that segment is
    # to win, company-wide. Legitimate for "how much real revenue did this
    # person close" -- but will always favor whoever works structurally
    # larger-ticket segments, which is expected and correct for a revenue
    # figure, NOT evidence of unfairness.
    if not won.empty:
        won = won.copy()
        won["difficulty_weight"] = won["segment"].map(difficulty_weights).fillna(1.0)
        won["adjusted_value"] = won["value"] * won["difficulty_weight"]
        adjusted_value = float(won["adjusted_value"].sum())

        # RELATIVE metric: express each won deal as a multiple of a TYPICAL
        # deal in its own segment before weighting, so a $300k Enterprise win
        # and a $15k SMB win can both read as "roughly a typical deal for my
        # segment" (~1.0) rather than the Enterprise deal automatically
        # dominating on raw dollars. This is the metric fairness comparisons
        # across segment-focus groups should use -- see run_fairness_audit().
        won["segment_avg_value"] = won["segment"].map(segment_avg_values).replace(0, np.nan)
        won["relative_units"] = won["value"] / won["segment_avg_value"]
        won["relative_adjusted_units"] = won["relative_units"] * won["difficulty_weight"]
        # MEAN, not sum: a sum is still sensitive to deal VOLUME, and segments
        # have structurally different sales-cycle lengths (Enterprise's
        # 60-150 day cycles mathematically allow fewer deals per year than
        # SMB's 10-35 day cycles) -- that's a structural constraint, not a
        # skill difference, and summing let volume re-enter through the side
        # door even after removing dollar-scale as a factor. The mean
        # expresses "on average, how does a won deal here compare to a
        # typical deal in this segment" -- ~1.0 is par, invariant to how
        # many deals this person happened to work.
        relative_index = float(won["relative_adjusted_units"].mean())
    else:
        adjusted_value = 0.0
        relative_index = 0.0

    normalized = {
        "difficulty_adjusted_value": round(adjusted_value, 2),
        # Value per deal WORKED (not just won) -- rewards efficient effort on
        # hard accounts rather than just raw win count. Still an absolute
        # dollar figure -- same segment-scale caveat as difficulty_adjusted_value.
        "value_per_deal_worked": round(adjusted_value / len(deals), 2) if len(deals) else 0.0,
        # Dimensionless: ~1.0 per won deal means "closed a typical deal for
        # my segment"; use THIS for cross-segment fairness comparisons.
        "relative_contribution_index": round(relative_index, 3),
    }

    return {
        "employee_id": employee_id,
        "raw": raw,
        "normalized": normalized,
        "activity_count": int(len(activities)),
        "sufficient_data": len(deals) >= MIN_DEALS_FOR_NARRATIVE,
    }


def build_leaderboard(bundle: dict = None) -> dict:
    """
    Raw + normalized metrics for every sales employee, side by side, plus the
    difficulty weights and segment average values that produced the
    normalized figures -- so the adjustment is always visible and auditable,
    never a hidden black box.
    """
    all_employees = db.get_all_employees()
    all_deals = db.get_crm_deals()
    all_activities = db.get_crm_activities()

    if all_deals.empty:
        return {"note": "No CRM deal data found -- run api/seed_crm.py first.", "employees": []}

    difficulty_weights = compute_segment_difficulty_weights(all_deals)
    segment_avg_values = compute_segment_avg_deal_values(all_deals)
    sales_employees = all_employees[all_employees["department"] == "Sales"] if not all_employees.empty else pd.DataFrame()

    results = []
    for _, emp in sales_employees.iterrows():
        metrics = compute_employee_metrics(emp["id"], all_deals, all_activities, difficulty_weights, segment_avg_values)
        metrics["full_name"] = emp["full_name"]
        metrics["role"] = emp["role"]
        results.append(metrics)

    # Sort by the NORMALIZED figure by default -- the whole point of this
    # feature is that the default view should not be the naive one.
    results.sort(key=lambda r: r["normalized"]["difficulty_adjusted_value"], reverse=True)

    return {"difficulty_weights": difficulty_weights, "segment_avg_deal_values": segment_avg_values, "employees": results}


# ------------------------------------------------------------------
# 4. Evidence-grounded narrative (never speculates about a person)
# ------------------------------------------------------------------
def generate_employee_narrative(full_name: str, metrics: dict) -> str:
    if not metrics["sufficient_data"]:
        return (
            f"Insufficient data to assess {full_name}'s performance "
            f"(only {metrics['raw']['total_deals']} deal(s) on record, minimum {MIN_DEALS_FOR_NARRATIVE} needed)."
        )

    prompt = (
        f"Write a 2-3 sentence, STRICTLY factual performance summary for {full_name}, "
        "based ONLY on the numbers below. Describe what the numbers show -- do not guess "
        "at effort, attitude, motivation, or character, and do not compare this person to "
        "others by name. If a number is not given, do not invent it.\n\n"
        f"RAW METRICS: {metrics['raw']}\n"
        f"DIFFICULTY-ADJUSTED METRICS: {metrics['normalized']}\n"
        f"ACTIVITY COUNT (calls/emails/meetings logged): {metrics['activity_count']}"
    )
    last_errors = {}
    for model_name in (chatbot.PRIMARY_MODEL, chatbot.FALLBACK_MODEL):
        config = types.GenerateContentConfig(
            system_instruction=(
                "You write short, strictly factual employee performance summaries from data. "
                "You never speculate about a person's effort, attitude, or character -- only "
                "describe what the numbers show. You never invent a number not provided."
            ),
            temperature=0.2,
            max_output_tokens=400,
            thinking_config=chatbot.thinking_config_for(model_name),
        )
        try:
            response = chatbot._client.models.generate_content(model=model_name, contents=prompt, config=config)
            return response.text
        except Exception as e:
            last_errors[model_name] = str(e)
            continue
    return f"(Narrative generation temporarily unavailable -- {last_errors})"


def get_employee_kpi(employee_id: str) -> dict:
    all_employees = db.get_all_employees()
    match = all_employees[all_employees["id"] == employee_id] if not all_employees.empty else pd.DataFrame()
    if match.empty:
        return {"error": f"No employee found with id {employee_id}"}
    full_name = match.iloc[0]["full_name"]

    all_deals = db.get_crm_deals()
    all_activities = db.get_crm_activities()
    if all_deals.empty:
        return {"error": "No CRM deal data found -- run api/seed_crm.py first."}

    difficulty_weights = compute_segment_difficulty_weights(all_deals)
    segment_avg_values = compute_segment_avg_deal_values(all_deals)
    metrics = compute_employee_metrics(employee_id, all_deals, all_activities, difficulty_weights, segment_avg_values)
    narrative = generate_employee_narrative(full_name, metrics)

    return {"full_name": full_name, "difficulty_weights_used": difficulty_weights, **metrics, "narrative": narrative}


# ------------------------------------------------------------------
# 5. Fairness audit -- does the NORMALIZED score still show a systematic
#    gap across segment-focus groups? A deterministic statistical check,
#    not an LLM judgment call.
# ------------------------------------------------------------------
def run_fairness_audit(bundle: dict = None, min_group_size: int = 2) -> dict:
    leaderboard = build_leaderboard(bundle)
    employees = leaderboard.get("employees", [])
    if len(employees) < 2:
        return {"status": "inconclusive", "reason": "Fewer than 2 employees with deal data -- nothing to compare."}

    difficulty_weights = leaderboard.get("difficulty_weights", {})

    # Group each employee by their DOMINANT segment (the one they worked most).
    groups = {}
    won_deal_counts = {}
    for emp in employees:
        segment_mix = emp["raw"].get("segment_mix", {})
        if not segment_mix:
            continue
        dominant_segment = max(segment_mix, key=segment_mix.get)
        # Group on the DIMENSIONLESS relative index, not the absolute dollar
        # figure -- comparing raw dollars across segments with structurally
        # different deal sizes (Enterprise deals are simply larger by
        # design) will always favor the bigger-ticket segment, which is
        # correct for a revenue figure but meaningless as a fairness signal.
        groups.setdefault(dominant_segment, []).append(emp["normalized"]["relative_contribution_index"])
        won_deal_counts.setdefault(dominant_segment, 0)
        won_deal_counts[dominant_segment] += emp["raw"].get("won_deals", 0)

    if len(groups) < 2:
        return {"status": "inconclusive", "reason": "All employees share the same dominant segment -- nothing to compare across."}

    # A "systematic" gap is a claim about a GROUP pattern. A group of one
    # person is not a group -- comparing single individuals and calling the
    # gap "bias" conflates one person's results with a pattern across
    # several people doing similar work. Require at least min_group_size
    # employees per dominant-segment group before treating a gap as
    # meaningful; report which groups don't yet have enough people rather
    # than silently including them.
    small_groups = {seg: len(vals) for seg, vals in groups.items() if len(vals) < min_group_size}
    comparable_groups = {seg: vals for seg, vals in groups.items() if len(vals) >= min_group_size}

    if len(comparable_groups) < 2:
        return {
            "status": "inconclusive",
            "reason": (
                f"Not enough employees per segment-focus group to test for a systematic pattern "
                f"(need >= {min_group_size} per group). Current group sizes: "
                f"{ {seg: len(vals) for seg, vals in groups.items()} }. A gap between individual "
                f"employees is not evidence of bias -- it could simply be a real performance "
                f"difference between two people. Seed more employees per segment focus to make "
                f"this audit meaningful."
            ),
            "group_sizes": {seg: len(vals) for seg, vals in groups.items()},
        }

    group_means = {seg: round(float(np.mean(vals)), 2) for seg, vals in comparable_groups.items()}
    overall_mean = float(np.mean([v for vals in comparable_groups.values() for v in vals]))

    flagged_low = {seg: mean for seg, mean in group_means.items() if overall_mean > 0 and mean < overall_mean * 0.6}
    flagged_high = {seg: mean for seg, mean in group_means.items() if overall_mean > 0 and mean > overall_mean * 1.67}

    # A gap is only as trustworthy as the sample it's computed from. With few
    # won deals in a group, ordinary random variation can easily produce a
    # 40%+ swing that looks like a "flag" but is really just noise -- this is
    # a DIFFERENT question from group_size (people count) above: a group can
    # have 2+ people and still have thin evidence if those people have only
    # closed a handful of deals each.
    MIN_WON_DEALS_FOR_CONFIDENCE = 20
    low_confidence_segments = {
        seg for seg in {**flagged_low, **flagged_high}
        if won_deal_counts.get(seg, 0) < MIN_WON_DEALS_FOR_CONFIDENCE
    }

    def _diagnose(seg):
        w = difficulty_weights.get(seg)
        n = won_deal_counts.get(seg, 0)
        confidence_note = (
            f" Based on only {n} won deal(s) in this group -- a gap this size is plausibly just "
            f"sampling noise at this sample size, not necessarily a real pattern."
            if n < MIN_WON_DEALS_FOR_CONFIDENCE else
            f" Based on {n} won deals in this group -- a reasonably sized sample."
        )
        if w is None:
            return f"'{seg}' has no difficulty weight on record.{confidence_note}"
        if w > 1.2:
            return f"'{seg}' carries a difficulty weight of {w} (above 1).{confidence_note}"
        if w < 0.8:
            return f"'{seg}' carries a difficulty weight of {w} (below 1, treated as easier).{confidence_note}"
        return f"'{seg}' carries a difficulty weight of {w} (close to neutral).{confidence_note}"

    interpretation_parts = []
    if flagged_high:
        interpretation_parts.append(
            "OVERCORRECTION: " + ", ".join(f"{seg} (mean {mean:,.2f})" for seg, mean in flagged_high.items())
            + " scores well ABOVE the overall average across a group of " + str(min_group_size) + "+ people. "
            + " ".join(_diagnose(s) for s in flagged_high)
        )
    if flagged_low:
        interpretation_parts.append(
            "UNDERCORRECTION: " + ", ".join(f"{seg} (mean {mean:,.2f})" for seg, mean in flagged_low.items())
            + " scores well BELOW the overall average across a group of " + str(min_group_size) + "+ people. "
            + " ".join(_diagnose(s) for s in flagged_low)
        )
    if not interpretation_parts:
        interpretation_parts.append(
            "No segment-focus group scores substantially above or below the overall average after "
            "difficulty-weighting -- the normalization appears to be correcting for account difficulty "
            "without over- or under-shooting."
        )
    if small_groups:
        interpretation_parts.append(
            f"NOTE: {list(small_groups.keys())} were excluded from this comparison for having fewer than "
            f"{min_group_size} employees -- results for those individuals are shown on the leaderboard but "
            f"not used to judge a systematic pattern."
        )

    flagged = {**flagged_low, **flagged_high}
    if flagged and flagged.keys() <= low_confidence_segments:
        status = "flagged_low_confidence"
    elif flagged:
        status = "flagged"
    else:
        status = "passed"

    return {
        "status": status,
        "group_means_by_dominant_segment": group_means,
        "overall_mean": round(overall_mean, 2),
        "difficulty_weights_used": difficulty_weights,
        "won_deal_counts_by_group": won_deal_counts,
        "flagged_groups_undercorrected": flagged_low,
        "flagged_groups_overcorrected": flagged_high,
        "groups_excluded_too_small": small_groups,
        "interpretation": " ".join(interpretation_parts),
    }
