"""Parse a messy Indian bank export into one clean DataFrame and validate it."""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .merchant import extract_merchant


class StatementError(Exception):
    """A readable problem with the uploaded file (shown in the UI, never a traceback)."""


# Column names differ between banks: add aliases here, nothing else changes (design Q10).
COLUMN_ALIASES = {
    "date": ["date", "txn date", "transaction date"],
    "narration": ["narration", "description", "particulars", "transaction remarks"],
    "ref": ["chq./ref.no.", "chq./ref.no", "chq/ref no", "ref no", "reference no"],
    "value_date": ["value dt", "value date"],
    "withdrawal": ["withdrawal amt.", "withdrawal amt", "withdrawal", "debit", "debit amount"],
    "deposit": ["deposit amt.", "deposit amt", "deposit", "credit", "credit amount"],
    "balance": ["closing balance", "balance", "closing bal"],
}
REQUIRED = ["date", "narration", "withdrawal", "deposit", "balance"]
# Explicit formats only; pandas is never allowed to guess day vs month.
DATE_FORMATS = ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")

SUMMARY_LABELS = [  # order matters: "dr count" must be tested before "debits"
    ("dr_count", ("dr count", "debit count")),
    ("cr_count", ("cr count", "credit count")),
    ("opening", ("opening",)),
    ("closing", ("closing",)),
    ("debits", ("debits", "total debit")),
    ("credits", ("credits", "total credit")),
]


@dataclass
class ParseResult:
    df: pd.DataFrame
    summary: dict
    errors: list = field(default_factory=list)       # unreadable rows, reported by statement row
    validation: list = field(default_factory=list)   # [{name, passed, detail}]


def _norm(c) -> str:
    return re.sub(r"\s+", " ", str(c)).strip().lower()


def _cell(row, j) -> str:
    return str(row[j]).strip() if j is not None and j < len(row) else ""


def parse_date(s: str):
    s = (s or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _num(s):
    s = str(s).strip().replace(",", "")
    if s in ("", "nan", "None", "NaN"):
        return None
    return float(s)  # ValueError propagates -> reported as a parse error


def find_header_row(rows):
    """Search for the first row that contains both a Date and a Narration column."""
    for i, row in enumerate(rows):
        cols = {}
        for j, c in enumerate(row):
            n = _norm(c)
            for key, aliases in COLUMN_ALIASES.items():
                if n in aliases and key not in cols:
                    cols[key] = j
        if "date" in cols and "narration" in cols:
            missing = [k for k in REQUIRED if k not in cols]
            if missing:
                raise StatementError(
                    f"Header row found at row {i + 1}, but these columns are missing: "
                    f"{', '.join(missing)}. Columns seen: {[str(c) for c in row if str(c).strip()]}")
            return i, cols
    raise StatementError("Could not find a header row containing 'Date' and 'Narration' columns. "
                         "Is this a bank statement export?")


def _is_separator(row) -> bool:
    cells = [str(c).strip() for c in row if str(c).strip()]
    return bool(cells) and all(re.fullmatch(r"[*\-=_\s]+", c) for c in cells)


def _label_of(cell):
    n = _norm(cell)
    for key, pats in SUMMARY_LABELS:
        if any(p in n for p in pats):
            return key
    return None


def _safe_num(s):
    try:
        return _num(s)
    except ValueError:
        return None


def parse_summary(rows) -> dict:
    """Handles 'labels in one row, values in the next' and 'label: value' layouts."""
    out = {}
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    for k, row in enumerate(rows):
        labels = [(j, _label_of(c)) for j, c in enumerate(row) if _label_of(c)]
        if len(labels) >= 3 and k + 1 < len(rows):
            for j, key in labels:
                v = _safe_num(_cell(rows[k + 1], j))
                if v is not None:
                    out.setdefault(key, v)
        elif len(labels) == 1:
            j, key = labels[0]
            for c in row[j + 1:]:
                v = _safe_num(c)
                if v is not None:
                    out.setdefault(key, v)
                    break
    for key in ("dr_count", "cr_count"):
        if key in out:
            out[key] = int(out[key])
    return out


def parse_rows(rows) -> ParseResult:
    hdr, cols = find_header_row(rows)
    i = hdr + 1
    while i < len(rows) and _is_separator(rows[i]):
        i += 1
    recs, errors = [], []
    while i < len(rows):
        row = rows[i]
        d = parse_date(_cell(row, cols["date"]))
        if d is None:          # first non-date row = end of transactions
            break
        sr = i + 1             # 1-based row number in the file
        try:
            w, dep, bal = (_num(_cell(row, cols[k])) for k in ("withdrawal", "deposit", "balance"))
            if (w is None) == (dep is None):
                errors.append(f"Row {sr}: exactly one of Withdrawal/Deposit must be filled "
                              f"(got withdrawal={w}, deposit={dep}).")
            elif bal is None:
                errors.append(f"Row {sr}: balance is blank.")
            else:
                narr = _cell(row, cols["narration"])
                recs.append({
                    "date": d, "narration": narr, "ref": _cell(row, cols.get("ref")),
                    "amount": -w if w is not None else dep, "balance": bal,
                    "direction": "debit" if w is not None else "credit",
                    "merchant": extract_merchant(narr), "stmt_row": sr,
                })
        except ValueError as e:
            errors.append(f"Row {sr}: unreadable number ({e}).")
        i += 1
    df = pd.DataFrame(recs, columns=["date", "narration", "ref", "amount", "balance",
                                     "direction", "merchant", "stmt_row"])
    if df.empty and not errors:
        raise StatementError("Header found, but no valid transaction rows (dd/mm/yy dates) below it.")
    df["date"] = pd.to_datetime(df["date"])
    summary = parse_summary(rows[i:])
    return ParseResult(df, summary, errors, validate(df, summary, errors))


def validate(df, summary, errors) -> list:
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("All rows readable", not errors, "OK" if not errors else "; ".join(errors[:10]))

    if "dr_count" in summary and "cr_count" in summary:
        exp = summary["dr_count"] + summary["cr_count"]
        add("Row count = Dr Count + Cr Count", len(df) == exp,
            f"parsed {len(df)}, summary says {summary['dr_count']} + {summary['cr_count']} = {exp}")
    else:
        add("Row count = Dr Count + Cr Count", False, "summary counts not found in file")

    if "debits" in summary and "credits" in summary:
        wd = round(-df.loc[df.amount < 0, "amount"].sum(), 2)
        dp = round(df.loc[df.amount > 0, "amount"].sum(), 2)
        ok = abs(wd - summary["debits"]) < 0.01 and abs(dp - summary["credits"]) < 0.01
        add("Sum of withdrawals / deposits matches summary", ok,
            f"withdrawals {wd:,.2f} vs {summary['debits']:,.2f}; deposits {dp:,.2f} vs {summary['credits']:,.2f}")
    else:
        add("Sum of withdrawals / deposits matches summary", False, "summary totals not found in file")

    if len(df):
        opening = summary.get("opening")
        prev = df["balance"].shift(1)
        if opening is not None:
            prev.iloc[0] = opening
        else:
            prev.iloc[0] = df["balance"].iloc[0] - df["amount"].iloc[0]
        diff = (prev + df["amount"] - df["balance"]).abs()
        bad = df.loc[diff > 0.01, "stmt_row"].tolist()
        note = "" if opening is not None else " (opening balance missing: first row not independently checked)"
        add("Running balance is consistent", not bad,
            ("every row reconciles" if not bad else f"balance breaks at statement rows {bad[:10]}") + note)
    return checks


def read_rows(file_obj, filename: str):
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            text = file_obj.read()
            text = text.decode("utf-8-sig", errors="replace") if isinstance(text, bytes) else text
            return list(csv.reader(io.StringIO(text)))
        if name.endswith((".xlsx", ".xls")):
            raw = pd.read_excel(file_obj, header=None, dtype=str, keep_default_na=False)
            return raw.values.tolist()
    except Exception as e:  # corrupted / wrong file type
        raise StatementError(f"Could not read '{filename}': {e}") from e
    raise StatementError("Unsupported file type. Upload a .xlsx or .csv file.")


def load_statement(file_obj, filename: str) -> ParseResult:
    return parse_rows(read_rows(file_obj, filename))
