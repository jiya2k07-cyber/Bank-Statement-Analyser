"""Combine the layers. Priority: Manual override > Rule > LLM (cached) > Uncategorized."""
import hashlib

import pandas as pd

from .categories import CATEGORIES
from .merchant import cache_key
from .rules import apply_rules

NONE_SOURCE = "—"


def tx_key(date, amount, narration) -> str:
    raw = f"{pd.Timestamp(date):%Y-%m-%d}|{amount:.2f}|{narration}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def categorise(df, rules, overrides, cache):
    out = df.copy()
    out["tx_key"] = [tx_key(d, a, n) for d, a, n in zip(out.date, out.amount, out.narration)]
    out["cache_key"] = [cache_key(m, d) for m, d in zip(out.merchant, out.direction)]
    rule_idx = apply_rules(out.narration.tolist(), rules)
    cats, srcs, reasons = [], [], []
    for k, ck, ri in zip(out.tx_key, out.cache_key, rule_idx):
        if overrides.get(k) in CATEGORIES:
            cats.append(overrides[k]); srcs.append("Manual"); reasons.append("set by hand")
        elif ri is not None:
            cats.append(rules[ri]["category"]); srcs.append("Rule")
            reasons.append(f"keyword '{rules[ri]['keyword']}'")
        elif ck in cache and cache[ck].get("category") in CATEGORIES:
            cats.append(cache[ck]["category"]); srcs.append("LLM"); reasons.append(cache[ck].get("reason", ""))
        else:
            cats.append("Uncategorized"); srcs.append(NONE_SOURCE); reasons.append("")
    out["category"], out["source"], out["reason"] = cats, srcs, reasons
    out["rule_idx"] = rule_idx
    return out


def pending_for_llm(cat_df):
    """Merchants (not rows) still unresolved after rules/overrides/cache. One narration each."""
    pend = {}
    for _, r in cat_df[cat_df.source == NONE_SOURCE].iterrows():
        pend.setdefault(r.cache_key, (r.narration, r.direction))
    return pend
