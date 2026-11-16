import io
import os
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analyser import store
from analyser.anomalies import flag_unusual
from analyser.categories import CATEGORY_LIST, MOVED_MONEY
from analyser.categoriser import categorise, pending_for_llm
from analyser.evaluate import evaluate
from analyser.llm import MODEL, api_key_available, categorise_pending
from analyser.parser import StatementError, load_statement
from analyser.recurring import MIN_OCCURRENCES, detect_recurring
from analyser.rules import sanitize, short_keyword_warnings

st.set_page_config(page_title="Bank Statement Analyser", layout="wide")


def inr(x, decimals=2):
    """Indian digit grouping: 1,23,456.00"""
    if pd.isna(x):
        return "-"
    s = f"{abs(x):.{decimals}f}"
    ip, _, fp = s.partition(".")
    if len(ip) > 3:
        ip = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", ip[:-3]) + "," + ip[-3:]
    return ("-" if x < 0 else "") + "₹" + ip + (f".{fp}" if decimals else "")


# API key: environment variable or Streamlit secrets, never in code.
try:
    if "ANTHROPIC_API_KEY" in st.secrets and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass  # no secrets file: fine

# ---------- persisted state ----------
if "rules_base" not in st.session_state:   # frozen copy the editor starts from
    r = store.load_json(store.RULES_PATH, None)
    if r is None:
        r = store.load_json(store.DEFAULT_RULES_PATH, [])
    st.session_state.rules_base = sanitize(r)
    st.session_state.rules_ver = 0
    st.session_state.llm_log = []
overrides = store.load_json(store.OVERRIDES_PATH, {})
cache = store.load_json(store.CACHE_PATH, {})

# ---------- sidebar: upload ----------
st.sidebar.title("Bank Statement Analyser")
up = st.sidebar.file_uploader("Bank statement (.xlsx or .csv)", type=["xlsx", "csv"])
st.sidebar.caption(f"LLM: {'API key found, model ' + MODEL if api_key_available() else 'no API key: unmatched rows stay Uncategorized'}")
if up is None:
    st.title("Bank Statement Analyser")
    st.info("Upload a statement in the sidebar to begin. (No file? Run `python make_sample.py`.)")
    st.stop()


@st.cache_data(show_spinner=False)
def _load(data: bytes, name: str):
    return load_statement(io.BytesIO(data), name)


try:
    res = _load(up.getvalue(), up.name)
except StatementError as e:
    st.error(f"Could not read this file: {e}")
    st.stop()

tabs = st.tabs(["Data & validation", "Rules", "Categories & LLM", "Dashboard",
                "Recurring", "Unusual payments", "Export", "Evaluation"])
t_data, t_rules, t_cat, t_dash, t_rec, t_unu, t_exp, t_eval = tabs

# ---------- Rules tab runs first so edits recategorise everything below immediately ----------
with t_rules:
    st.subheader("Keyword rules")
    st.caption("A rule matches when its keyword appears anywhere in the narration (case-insensitive). "
               "If several match, the **longest keyword wins**; a tie goes to the rule listed first. "
               "Tick *whole_word* for short keywords so 'uber' does not match inside another word.")
    edited = st.data_editor(
        pd.DataFrame(st.session_state.rules_base, columns=["keyword", "category", "whole_word"]),
        num_rows="dynamic", use_container_width=True, hide_index=True,
        key=f"rules_ed_{st.session_state.rules_ver}",
        column_config={"category": st.column_config.SelectboxColumn(options=CATEGORY_LIST, required=True),
                       "whole_word": st.column_config.CheckboxColumn(default=False)})
    rules = sanitize(edited.fillna({"whole_word": False}).to_dict("records"))
    if rules != store.load_json(store.RULES_PATH, None):
        store.save_json(store.RULES_PATH, rules)       # persists across restarts
    for kw in short_keyword_warnings(rules):
        st.warning(f"Keyword '{kw}' is short and may match unrelated narrations. Consider whole_word.")

df = res.df
base = categorise(df, rules, {}, cache)
cdf = categorise(df, rules, overrides, cache)

with t_rules:
    counts = cdf.rule_idx.value_counts()
    stats = pd.DataFrame([{"keyword": r["keyword"], "category": r["category"], "matched": int(counts.get(i, 0))}
                          for i, r in enumerate(rules)])
    c1, c2 = st.columns([2, 1])
    c1.dataframe(stats, hide_index=True, use_container_width=True)
    c2.metric("Rows matching no rule", int(cdf.rule_idx.isna().sum()))
    c2.metric("Rows matched by a rule", int(cdf.rule_idx.notna().sum()))

# ---------- Data & validation ----------
with t_data:
    st.subheader("Validation")
    for c in res.validation:
        (st.success if c["passed"] else st.error)(f"{'PASS' if c['passed'] else 'FAIL'}: {c['name']}. {c['detail']}")
    if res.errors:
        st.error("Rows that could not be parsed:\n\n" + "\n".join(f"- {e}" for e in res.errors))
    st.subheader("Cleaned transactions")
    show = df.drop(columns=["ref"]).copy()
    show["amount"] = show.amount.map(inr); show["balance"] = show.balance.map(inr)
    st.dataframe(show, use_container_width=True, hide_index=True)

# ---------- Categories & LLM ----------
with t_cat:
    st.subheader("LLM categorisation of unmatched merchants")
    pend = pending_for_llm(cdf)
    c1, c2, c3 = st.columns(3)
    c1.metric("Merchants waiting for LLM", len(pend))
    c2.metric("API calls this session", sum(x["api_calls"] for x in st.session_state.llm_log))
    c3.metric("Merchants in LLM cache", len(cache))
    if st.button("Categorise unmatched with LLM", disabled=not pend):
        if not api_key_available():
            st.warning("No ANTHROPIC_API_KEY set: unmatched rows stay Uncategorized.")
        else:
            with st.spinner("Calling the LLM in batches..."):
                s = categorise_pending(pend, cache)
            store.save_json(store.CACHE_PATH, cache)
            st.session_state.llm_log.append(s)
            st.rerun()
    if st.session_state.llm_log:
        last = st.session_state.llm_log[-1]
        st.caption(f"Last run: {last['api_calls']} API call(s), {last['merchants_sent']} merchants sent, "
                   f"{last['rejected']} invalid labels rejected, {last['unanswered']} unanswered"
                   + (f", error: {last['error']}" if last["error"] else ""))
    llm_rows = cdf[cdf.source == "LLM"].drop_duplicates("merchant")
    if len(llm_rows):
        st.markdown("**Turn an LLM answer into a rule** (fewer rows reach the LLM next time)")
        pick = st.selectbox("Merchant", llm_rows.merchant.tolist())
        row = llm_rows[llm_rows.merchant == pick].iloc[0]
        if st.button(f"Save rule: '{pick.lower()}' → {row.category}"):
            st.session_state.rules_base = sanitize(rules + [{"keyword": pick.lower(), "category": row.category, "whole_word": False}])
            st.session_state.rules_ver += 1
            store.save_json(store.RULES_PATH, st.session_state.rules_base)
            st.rerun()

    st.subheader("All transactions: override any category by hand")
    tbl = cdf[["tx_key", "date", "merchant", "amount", "category", "source", "reason", "narration"]].reset_index(drop=True)
    ed = st.data_editor(
        tbl.drop(columns=["tx_key"]), hide_index=True, use_container_width=True, height=420, key="tx_editor",
        disabled=["date", "merchant", "amount", "source", "reason", "narration"],
        column_config={"category": st.column_config.SelectboxColumn(options=CATEGORY_LIST, required=True),
                       "amount": st.column_config.NumberColumn(format="%.2f")})
    changed = ed.index[ed.category != tbl.category]
    if len(changed):
        base_cat = base.reset_index(drop=True).category
        for i in changed:
            k = tbl.tx_key[i]
            if ed.category[i] == base_cat[i]:
                overrides.pop(k, None)
            else:
                overrides[k] = ed.category[i]
        store.save_json(store.OVERRIDES_PATH, overrides)
        st.rerun()
    if st.button("Clear all manual overrides", disabled=not overrides):
        store.save_json(store.OVERRIDES_PATH, {})
        st.rerun()
    st.caption("Source counts: " + ", ".join(f"{k}: {v}" for k, v in cdf.source.value_counts().items()))

# ---------- sidebar filters ----------
st.sidebar.header("Filters")
dmin, dmax = cdf.date.min().date(), cdf.date.max().date()
dr = st.sidebar.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
d0, d1 = (dr[0], dr[1]) if isinstance(dr, tuple) and len(dr) == 2 else (dmin, dmax)
cats_sel = st.sidebar.multiselect("Categories", CATEGORY_LIST, default=CATEGORY_LIST)
include_moved = st.sidebar.toggle("Include Transfers, Investments, Cash Withdrawal in spending", value=False)

f = cdf[(cdf.date.dt.date >= d0) & (cdf.date.dt.date <= d1) & cdf.category.isin(cats_sel)].copy()
f["month"] = f.date.dt.to_period("M").astype(str)
excluded = {"Income"} | (set() if include_moved else MOVED_MONEY)
spend = f[~f.category.isin(excluded)].copy()
spend["spend"] = -spend.amount           # refunds (positive) reduce spend in their category
spend["amt"] = spend.spend.map(inr)


def style(fig):
    fig.update_layout(yaxis_tickprefix="₹", margin=dict(t=40, b=10))
    return fig


# ---------- Dashboard ----------
with t_dash:
    if spend.empty:
        st.info("No spending in the selected filters.")
    else:
        st.subheader("Monthly spend by category")
        m = spend.groupby(["month", "category"], as_index=False).spend.sum()
        m["amt"] = m.spend.map(inr)
        st.plotly_chart(style(px.bar(m, x="month", y="spend", color="category", barmode="stack",
                                     hover_data={"amt": True, "spend": False})), use_container_width=True)

        a, b = st.columns(2)
        with a:
            st.subheader("Top 10 merchants by spend")
            tm = spend[spend.amount < 0].groupby("merchant", as_index=False).spend.sum().nlargest(10, "spend")
            tm["amt"] = tm.spend.map(inr)
            fig = px.bar(tm.sort_values("spend"), x="spend", y="merchant", orientation="h",
                         hover_data={"amt": True, "spend": False})
            fig.update_layout(xaxis_tickprefix="₹", margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)
        with b:
            st.subheader("Income vs expenses")
            inc = f[f.category == "Income"].groupby("month").amount.sum()
            exp = spend.groupby("month").spend.sum()
            ie = pd.DataFrame({"income": inc, "expenses": exp}).fillna(0)
            ie["net"] = ie.income - ie.expenses
            fig = go.Figure([go.Bar(x=ie.index, y=ie.income, name="Income"),
                             go.Bar(x=ie.index, y=ie.expenses, name="Expenses"),
                             go.Scatter(x=ie.index, y=ie.net, name="Net savings", mode="lines+markers+text",
                                        text=[inr(v, 0) for v in ie.net], textposition="top center")])
            st.plotly_chart(style(fig), use_container_width=True)

        st.subheader("Month-over-month comparison")
        months = sorted(spend.month.unique())
        if len(months) < 2:
            st.caption("Need at least two months in the selected range.")
        else:
            c1, c2 = st.columns(2)
            ma = c1.selectbox("Month A", months, index=0)
            mb = c2.selectbox("Month B", months, index=len(months) - 1)
            p = spend.pivot_table(index="category", columns="month", values="spend", aggfunc="sum", fill_value=0)
            cmp_ = pd.DataFrame({"A": p.get(ma, 0), "B": p.get(mb, 0)}, index=p.index)
            cmp_["change"] = cmp_.B - cmp_.A
            cmp_["pct"] = cmp_.apply(lambda r: (r.change / r.A * 100) if r.A else float("nan"), axis=1)
            out = pd.DataFrame({ma: cmp_.A.map(inr), mb: cmp_.B.map(inr), "Change (₹)": cmp_.change.map(inr),
                                "Change (%)": cmp_.pct.map(lambda v: "-" if pd.isna(v) else f"{v:+.1f}%")})
            st.dataframe(out, use_container_width=True)

# ---------- Recurring ----------
rec = detect_recurring(cdf)
with t_rec:
    st.subheader("Recurring charges")
    st.caption(f"A merchant is recurring if it has at least {MIN_OCCURRENCES} debits at a regular interval "
               "(detected, not assumed). Subscriptions are highlighted.")
    if rec.empty:
        st.info("No recurring charges found.")
    else:
        r = rec.copy()
        r["typical_amount"] = r.typical_amount.map(inr)
        for c in ("last_date", "next_expected", "first_date"):
            r[c] = r[c].dt.strftime("%d %b %Y")
        r["amount_varies"] = r.amount_varies.map({True: "varies", False: "fixed"})
        view = r[["merchant", "category", "typical_amount", "amount_varies", "interval", "interval_days",
                  "occurrences", "last_date", "next_expected", "is_subscription"]]
        st.dataframe(view.style.apply(lambda row: ["background-color: #fff3cd; color: #000" if row.is_subscription else "" for _ in row], axis=1),
                     use_container_width=True, hide_index=True)
        st.metric("Subscriptions found", int(rec.is_subscription.sum()))

# ---------- Unusual ----------
with t_unu:
    st.subheader("Unusual one-off payments")
    k = st.slider("Strictness k (threshold = Q3 + k × IQR of your debits; lower flags more)", 0.5, 6.0, 3.0, 0.5)
    flagged, thr = flag_unusual(spend[spend.amount < 0], rec.merchant.tolist() if len(rec) else [], k)
    if pd.isna(thr):
        st.info("Not enough debits to compute a threshold.")
    else:
        st.metric("Current threshold", inr(thr))
        if flagged.empty:
            st.success("Nothing unusual at this threshold.")
        else:
            fl = flagged[["date", "merchant", "spend", "category"]].copy()
            fl["spend"] = fl.spend.map(inr)
            st.dataframe(fl.rename(columns={"spend": "amount"}), hide_index=True, use_container_width=True)

# ---------- Export ----------
with t_exp:
    out = cdf[["date", "narration", "merchant", "amount", "direction", "category", "source", "reason"]]
    st.download_button("Download categorised transactions (CSV)", out.to_csv(index=False).encode("utf-8"),
                       "categorised_transactions.csv", "text/csv")
    st.dataframe(out, hide_index=True, use_container_width=True)

# ---------- Evaluation ----------
with t_eval:
    st.subheader("Score against answer_key.xlsx")
    st.caption("Only open the key after the LLM step works end to end.")
    key_file = st.file_uploader("answer_key.xlsx", type=["xlsx"], key="key")
    if key_file:
        try:
            key = pd.read_excel(key_file, sheet_name="Labels")
            rr = evaluate(cdf, key, rec, flagged)
            st.metric("Overall accuracy", f"{rr['overall_accuracy']:.1%}", f"{rr['joined_rows']} rows joined")
            if "by_tier" in rr:
                st.dataframe(rr["by_tier"], hide_index=True)
            if "ambiguous" in rr:
                st.write("Ambiguous tier:", rr["ambiguous"])
            st.write("Most common mistakes"); st.dataframe(rr["confusion"], hide_index=True)
            for name in ("recurring", "one_offs"):
                if name in rr:
                    st.write(name, rr[name])
        except Exception as e:
            st.error(f"Could not evaluate: {e}")
