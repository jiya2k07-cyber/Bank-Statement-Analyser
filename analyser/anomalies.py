"""Unusual one-off payments: debit amount > Q3 + k * IQR of the person's own debits.
Robust to the very outliers we are hunting (unlike mean/std), scale-free (no fixed rupee
amount), and a single slider k controls strictness. Recurring merchants are never flagged."""
import pandas as pd


def flag_unusual(spend: pd.DataFrame, recurring_merchants, k: float = 3.0):
    """spend: rows with a positive 'spend' column. Returns (flagged_df, threshold)."""
    d = spend[spend.spend > 0]
    if len(d) < 4:
        return d.iloc[0:0], float("nan")
    q1, q3 = d.spend.quantile(0.25), d.spend.quantile(0.75)
    threshold = float(q3 + k * (q3 - q1))
    flagged = d[(d.spend > threshold) & (~d.merchant.isin(set(recurring_merchants)))]
    return flagged.sort_values("spend", ascending=False), threshold
