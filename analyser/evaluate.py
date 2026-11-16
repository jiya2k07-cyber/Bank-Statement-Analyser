"""Score the app's output against answer_key.xlsx (Labels sheet). Column names are matched
loosely because the key's exact headers were not known when this was written."""
import pandas as pd


def _col(df, *needles):
    for c in df.columns:
        if all(n in str(c).lower() for n in needles):
            return c
    return None


def _truthy(v) -> bool:
    return str(v).strip().lower() not in ("", "nan", "none", "false", "0", "no", "-")


def evaluate(pred: pd.DataFrame, key: pd.DataFrame, recurring: pd.DataFrame, flagged: pd.DataFrame):
    rowc = _col(key, "row")
    catc = _col(key, "expected") or _col(key, "categ")
    tierc = _col(key, "tier") or _col(key, "difficulty")
    if not (rowc and catc):
        raise ValueError(f"Could not find row/category columns in key. Columns: {list(key.columns)}")
    k = key.rename(columns={rowc: "stmt_row", catc: "expected"})
    m = pred.merge(k, on="stmt_row", how="inner")
    m["correct"] = m.category == m.expected
    out = {"joined_rows": len(m), "overall_accuracy": float(m.correct.mean()) if len(m) else float("nan")}
    if tierc:
        t = m.groupby(tierc).correct.agg(["mean", "sum", "count"]).rename(
            columns={"mean": "accuracy", "sum": "correct", "count": "rows"})
        out["by_tier"] = t.reset_index()
        amb = m[m[tierc].astype(str).str.lower().str.contains("ambig")]
        out["ambiguous"] = {
            "rows": len(amb),
            "correctly_left_uncategorized": int((amb.category == "Uncategorized").sum()),
            "guessed_a_label": int((amb.category != "Uncategorized").sum()),
        }
    wrong = m[~m.correct]
    out["confusion"] = (wrong.groupby(["expected", "category"]).size().reset_index(name="count")
                        .rename(columns={"category": "predicted"})
                        .sort_values("count", ascending=False).head(20))
    rc = _col(key, "recurring")
    if rc:
        planted = k[k[rc].map(_truthy)].merge(pred[["stmt_row", "merchant"]], on="stmt_row")
        found = set(recurring.merchant) if len(recurring) else set()
        names = sorted(set(planted.merchant))
        out["recurring"] = {"found": [n for n in names if n in found], "missed": [n for n in names if n not in found]}
    oc = _col(key, "one") or _col(key, "unusual")
    if oc:
        planted_rows = set(k.loc[k[oc].map(_truthy), "stmt_row"])
        flagged_rows = set(flagged.stmt_row) if len(flagged) else set()
        out["one_offs"] = {"planted": len(planted_rows), "flagged_correctly": len(planted_rows & flagged_rows),
                           "missed": sorted(planted_rows - flagged_rows),
                           "false_alarms": len(flagged_rows - planted_rows)}
    return out
