"""Generate a FICTIONAL statement in the same layout as the assignment's sample, so the app
and tests can be run without the real file. Usage: python make_sample.py"""
import random
import pandas as pd

random.seed(7)
HEAD = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]


def upi(name, vpa, amt, d):
    return (f"UPI-{name}{vpa}-UTIB0000456-{random.randint(10**11, 10**12 - 1)}-UPI", amt, d)


def build():
    tx = []  # (narration, signed amount, datetime.date)
    for m in range(4, 10):
        tx.append((f"NEFT CR-HDFC0000001-ACME TECHNOLOGIES PVT LTD-SALARY {m}", 85000.0, pd.Timestamp(2026, m, 1)))
        tx.append(upi("ARJUN MEHTA", "arjun@okaxis", -25000.0, pd.Timestamp(2026, m, 3)))
        tx.append(upi("NETFLIX COMMUNICATIONS", "netflix@icici", -(649.0 if m < 8 else 699.0), pd.Timestamp(2026, m, 6)))
        tx.append(upi("SPOTIFY INDIA", "spotify@hdfcbank", -119.0, pd.Timestamp(2026, m, 9 + (m % 2))))
        tx.append(("ACH D- HDFCMUTUALFUND-000123", -5000.0, pd.Timestamp(2026, m, 5)))
        tx.append((f"BIL/BPAY/00012{m}/BESCOM ELECTRICITY", -float(random.randint(900, 2200)), pd.Timestamp(2026, m, 12)))
        tx.append(("INT.PD 01/{:02d}/26".format(m), 210.5, pd.Timestamp(2026, m, 28)))
        tx.append(("SMS ALERT CHARGES", -17.7, pd.Timestamp(2026, m, 27)))
        for _ in range(random.randint(3, 5)):
            tx.append(upi("SWIGGY LIMITED", "swiggy.upi@icici", -float(random.randint(180, 750)), pd.Timestamp(2026, m, random.randint(1, 28))))
        for _ in range(2):
            tx.append(upi("BLINKIT", "blinkit@yesbank", -float(random.randint(250, 900)), pd.Timestamp(2026, m, random.randint(1, 28))))
        tx.append((f"POS 525293XXXXXX1234 AMAZON PAY INDIA POS DEBIT", -float(random.randint(300, 3000)), pd.Timestamp(2026, m, random.randint(1, 28))))
        tx.append(("ATW-525293XXXXXX1234-HDFC BANK ATM", -3000.0, pd.Timestamp(2026, m, random.randint(1, 28))))
        tx.append(upi("RAHUL SHARMA", "rahul9876@ybl", -float(random.choice([500, 1200, 2000])), pd.Timestamp(2026, m, random.randint(1, 28))))
        tx.append(upi("PAYTM QR", "paytmqr281005050101@paytm", -float(random.randint(60, 400)), pd.Timestamp(2026, m, random.randint(1, 28))))
    tx.append(("POS 525293XXXXXX1234 SOUTHERN AIRWAYS POS DEBIT", -48500.0, pd.Timestamp(2026, 8, 14)))  # one-off
    tx.sort(key=lambda t: t[2])
    bal, opening, rows = 42350.75, 42350.75, []
    for narr, amt, d in tx:
        bal = round(bal + amt, 2)
        ds = d.strftime("%d/%m/%y")
        vd = (d + pd.Timedelta(days=1)).strftime("%d/%m/%y") if narr.startswith("POS") else ds
        rows.append([ds, narr, f"{random.randint(0, 10**16 - 1):016d}", vd,
                     f"{-amt:.2f}" if amt < 0 else "", f"{amt:.2f}" if amt > 0 else "", f"{bal:.2f}"])
    dr = [r for r in rows if r[4]]; cr = [r for r in rows if r[5]]
    grid = [["EXAMPLE BANK LTD"], ["Account Holder: A. SAMPLE"], ["Account No: XXXXXXXX1234"],
            ["Statement From: 01/04/2026 To: 30/09/2026"], [""], HEAD, ["********"] * 7]
    grid += rows + [[""]]
    grid += [["STATEMENT SUMMARY"],
             ["Opening Balance", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"],
             [f"{opening:.2f}", len(dr), len(cr), f"{sum(float(r[4]) for r in dr):.2f}",
              f"{sum(float(r[5]) for r in cr):.2f}", rows[-1][6]],
             [""], ["This is a computer generated statement."]]
    return grid


if __name__ == "__main__":
    g = build()
    w = max(len(r) for r in g)
    g = [r + [""] * (w - len(r)) for r in g]
    pd.DataFrame(g).to_excel("sample_statement.xlsx", header=False, index=False)
    pd.DataFrame(g).to_csv("sample_statement.csv", header=False, index=False)
    print(f"wrote sample_statement.xlsx / .csv ({len(g)} grid rows)")
