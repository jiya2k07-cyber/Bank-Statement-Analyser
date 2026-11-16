"""Recurring-charge detection.

Group debits by cleaned merchant (NOT by amount, so a price change or a varying bill never
splits one subscription). A group is recurring if it has >= MIN_OCCURRENCES debits and its gaps
between payments are regular around one standard period."""
import numpy as np
import pandas as pd

MIN_OCCURRENCES = 3
PERIODS = {"weekly": 7, "fortnightly": 14, "monthly": 30.4, "bi-monthly": 61,
           "quarterly": 91, "half-yearly": 182, "yearly": 365}
REGULAR_SHARE = 0.7      # share of gaps that must sit near the typical gap


def _tolerance(period: float) -> float:
    # 12% of the period, never less than 3 days: monthly -> +/-3.6d covers 28-31 day months
    # plus a weekend slip, weekly stays tight at 3d.
    return max(3.0, 0.12 * period)


def detect_recurring(df: pd.DataFrame, min_occurrences: int = MIN_OCCURRENCES) -> pd.DataFrame:
    cols = ["merchant", "category", "typical_amount", "interval_days", "interval", "occurrences",
            "last_date", "next_expected", "amount_varies", "is_subscription", "first_date"]
    rows = []
    debits = df[df.amount < 0]
    for merchant, g in debits.groupby("merchant"):
        g = g.sort_values("date")
        if len(g) < min_occurrences:
            continue
        gaps = np.diff(g["date"].values).astype("timedelta64[D]").astype(float)
        typical = float(np.median(gaps))
        label, period = min(PERIODS.items(), key=lambda kv: abs(kv[1] - typical))
        if abs(typical - period) > _tolerance(period):
            continue                                     # irregular rhythm (e.g. frequent food orders)
        share = np.mean(np.abs(gaps - typical) <= _tolerance(period))
        if share < REGULAR_SHARE:
            continue
        amounts = (-g["amount"]).to_numpy()
        category = g["category"].mode().iat[0] if "category" in g else ""
        last = g["date"].max()
        rows.append({
            "merchant": merchant, "category": category,
            "typical_amount": float(np.median(amounts)), "interval_days": round(typical, 1),
            "interval": label, "occurrences": len(g), "last_date": last,
            "next_expected": last + pd.Timedelta(days=round(typical)),
            "amount_varies": bool(amounts.max() > 1.15 * amounts.min()),
            "is_subscription": category == "Subscriptions", "first_date": g["date"].min(),
        })
    return pd.DataFrame(rows, columns=cols).sort_values(
        ["is_subscription", "typical_amount"], ascending=False).reset_index(drop=True)
