import pandas as pd

from analyser.recurring import detect_recurring


def make(merchant, dates, amounts, cat="Subscriptions"):
    return pd.DataFrame({"merchant": merchant, "date": pd.to_datetime(dates),
                         "amount": [-a for a in amounts], "category": cat})


def test_monthly_with_price_change_is_one_group():
    df = make("NETFLIX", ["2026-04-06", "2026-05-06", "2026-06-06", "2026-07-06", "2026-08-06"],
              [649, 649, 649, 699, 699])
    r = detect_recurring(df)
    assert len(r) == 1 and r.occurrences[0] == 5 and r.interval[0] == "monthly" and r.is_subscription[0]


def test_varying_amounts_and_weekend_slip_still_recurring():
    df = make("POWER", ["2026-04-12", "2026-05-14", "2026-06-12", "2026-07-15"], [900, 2100, 1500, 1200], "Utilities & Bills")
    r = detect_recurring(df)
    assert len(r) == 1 and r.amount_varies[0] and not r.is_subscription[0]


def test_two_occurrences_is_not_recurring():
    assert detect_recurring(make("X", ["2026-04-01", "2026-05-01"], [10, 10])).empty


def test_irregular_merchant_is_not_recurring():
    df = make("FOOD", ["2026-04-01", "2026-04-03", "2026-04-20", "2026-04-22", "2026-05-15"], [100] * 5, "Food & Dining")
    assert detect_recurring(df).empty


def test_quarterly_interval_detected_not_assumed_monthly():
    df = make("INSURER", ["2026-01-10", "2026-04-10", "2026-07-10"], [5000] * 3, "Insurance")
    assert detect_recurring(df).interval[0] == "quarterly"


def test_credits_ignored():
    df = make("SALARY", ["2026-04-01", "2026-05-01", "2026-06-01"], [1, 1, 1])
    df["amount"] = df["amount"].abs()
    assert detect_recurring(df).empty
