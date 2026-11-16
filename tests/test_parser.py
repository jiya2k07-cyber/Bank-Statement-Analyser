import pandas as pd
import pytest

from analyser.parser import StatementError, parse_rows

HEAD = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]


def grid(tx, summary=("1000.00", 1, 1, "100.00", "300.00", "1200.00")):
    g = [["BANK"], ["Holder"], [""], HEAD, ["***"] * 7]
    g += tx + [[""], ["Opening Balance", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"], list(summary), ["footer"]]
    return g


GOOD = [["03/04/26", "UPI-SWIGGY LIMITEDswiggy.upi@icici-UTIB0000456-1-UPI", "0082056888155978", "04/04/26", "100.00", "", "900.00"],
        ["05/04/26", "NEFT CR-HDFC0000001-ACME-SALARY", "0000000000000001", "05/04/26", "", "300.00", "1200.00"]]


def test_date_is_day_first_and_header_found_by_search():
    r = parse_rows(grid(GOOD))
    assert r.df.date.iloc[0] == pd.Timestamp(2026, 4, 3)      # not 4 March
    assert list(r.df.direction) == ["debit", "credit"]
    assert list(r.df.amount) == [-100.0, 300.0]


def test_ref_kept_as_text_with_leading_zeros():
    assert parse_rows(grid(GOOD)).df.ref.iloc[0] == "0082056888155978"


def test_blank_amounts_handled_and_all_validations_pass():
    r = parse_rows(grid(GOOD))
    assert all(c["passed"] for c in r.validation), r.validation


def test_both_amounts_filled_is_reported_error():
    bad = [list(GOOD[0])]; bad[0][5] = "5.00"
    r = parse_rows(grid(bad))
    assert r.errors and "Row 6" in r.errors[0]
    assert not r.validation[0]["passed"]


def test_neither_amount_filled_is_error():
    bad = [list(GOOD[0])]; bad[0][4] = ""
    assert parse_rows(grid(bad)).errors


def test_row_count_mismatch_fails_validation():
    r = parse_rows(grid(GOOD, summary=("1000.00", 5, 1, "100.00", "300.00", "1200.00")))
    assert not [c for c in r.validation if c["name"].startswith("Row count")][0]["passed"]


def test_sum_mismatch_fails_validation():
    r = parse_rows(grid(GOOD, summary=("1000.00", 1, 1, "999.00", "300.00", "1200.00")))
    assert not [c for c in r.validation if c["name"].startswith("Sum")][0]["passed"]


def test_balance_break_is_detected_and_row_reported():
    bad = [list(r) for r in GOOD]; bad[1][6] = "5000.00"
    c = [c for c in parse_rows(grid(bad)).validation if "balance" in c["name"].lower()][0]
    assert not c["passed"] and "7" in c["detail"]


def test_wrong_columns_give_readable_error():
    with pytest.raises(StatementError):
        parse_rows([["foo", "bar"], ["1", "2"]])


def test_stops_at_first_non_date_row():
    assert len(parse_rows(grid(GOOD)).df) == 2
