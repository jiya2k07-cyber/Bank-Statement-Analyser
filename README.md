# Bank Statement Analyser

A Streamlit app that parses an Indian-style bank statement export (.xlsx or .csv), validates it,
puts every transaction into one of 20 categories (keyword rules first, then a batched, cached LLM
that is allowed to say "Uncategorized"), and shows where the money went, including recurring charges
and unusual one-off payments.

> Screenshot: _add `docs/dashboard.png` after your first run_

## Run it
```bash
pip install -r requirements.txt
python make_sample.py                 # optional: fictional statement in the same layout
export ANTHROPIC_API_KEY=...          # optional; or put it in .streamlit/secrets.toml
streamlit run app.py
pytest                                # or: python run_tests.py
```
Without an API key or internet the app still works: unmatched rows stay Uncategorized.
State lives in `data/` (`rules.json`, `overrides.json`, `llm_cache.json`); all git-ignored.

## Layout
| File | Job |
|---|---|
| `analyser/parser.py` | find header, parse rows, summary block, 4 validation checks |
| `analyser/merchant.py` | per-format merchant extraction + LLM cache key |
| `analyser/rules.py` | keyword rules, conflict policy |
| `analyser/llm.py` | prompt, batching, JSON parsing, closed-list check, retry, cache fill |
| `analyser/categoriser.py` | Manual > Rule > LLM > Uncategorized |
| `analyser/recurring.py`, `anomalies.py` | F5, F6 |
| `analyser/evaluate.py` | scoring against `answer_key.xlsx` (Evaluation tab) |

## Design answers (section 6)
1. **Header row.** Scan rows top-down for the first one containing both a Date and a Narration column
   (matched through an alias table). The asterisk row is skipped; transactions end at the first row whose Date is not
   a valid date; the rest is parsed as the summary block. No row numbers are hardcoded.
2. **Merchant name.** One extractor per prefix (UPI, POS, NEFT/IMPS, ACH, BIL/BPAY, ATW). In UPI the name and the
   lowercase UPI ID are glued together, so a regex splits at the lowercase run that ends in `@bank`. Unrecognised
   formats fall back to the first few non-numeric words, so nothing crashes and plain-text bank charges still get a stable name.
3. **Short/broad keywords.** A per-rule `whole_word` option, a warning for keywords under 4 characters, and a deterministic
   policy: the *longest* matching keyword wins (more specific), ties go to the earlier rule.
4. **Whole narration vs merchant only.** I match the whole narration, as the brief specifies. It catches keywords in remarks,
   but can hit the UPI ID or remark by accident (a friend's remark "uber share"). Merchant-only matching is cleaner but misses
   formats where extraction fails. `whole_word` limits the damage of the first.
5. **Cache key.** `direction|MERCHANT` with digit runs of 3+ masked to `#`, so merchants whose names carry changing IDs
   share a key. Direction is part of the key because a refund and a purchase are different questions. Merchants that are
   still unique per transaction just cost one extra row in a batch and will usually be Uncategorized anyway.
6. **Allowing "I don't know".** The system prompt says an uninformative narration (person's name, QR/terminal code, opaque ID) must be
   `Uncategorized` and that a wrong confident label is worse. Code rejects anything outside the 20 categories. To check it
   actually does so, the Evaluation tab counts, for the Ambiguous tier, how many were left Uncategorized vs guessed.
7. **Recurring.** Same cleaned merchant, at least 3 debits (two points give one gap, which proves nothing; three give two gaps
   that can agree). The median gap must be within tolerance of a standard period (weekly, fortnightly, monthly, bi-monthly,
   quarterly, half-yearly, yearly) and at least 70% of gaps must sit near it. Tolerance is max(3 days, 12% of period):
   about ±3.6 days for monthly (28–31 day months plus a weekend slip). Grouping ignores amount, so price rises and
   varying bills never split a subscription; instead the amount is shown as typical (median) and flagged "varies".
8. **Unusually large.** Debit amount > Q3 + k·IQR of the person's own spending (default k = 3, adjustable, threshold shown).
   It is robust (the outliers being hunted do not inflate the yardstick, unlike mean/std), scales with the person, and
   a fixed rupee amount would be wrong for everyone. Recurring merchants are excluded.
9. **Saved state.** JSON files in `data/`, written atomically. Missing file → defaults (rules seed from `default_rules.json`,
   empty overrides/cache). Corrupt file → renamed to `*.corrupt-<time>` and treated as missing, so the app starts and nothing is lost silently.
10. **Second bank.** Add names to `COLUMN_ALIASES` in `parser.py`. If a bank uses a single signed Amount column or
    different date formats, add a small adapter producing the same clean frame; nothing downstream changes.

## Other decisions
- Spending = −amount of rows not in Income (and not in Transfers/Investments/Cash Withdrawal unless toggled). Refunds are positive amounts in their
  original category, so they reduce that category's spend.
- Manual overrides are keyed by a hash of date + amount + narration, so they survive re-uploading the same statement.
- Only `{id, narration, direction}` is sent to the LLM; never balance, account or reference numbers.

## Evaluation (fill in after running the Evaluation tab with `answer_key.xlsx`)
| Metric | First run | After fixes |
|---|---|---|
| Overall accuracy | | |
| Keyword / Needs LLM / Ambiguous accuracy | | |
| Ambiguous: left Uncategorized / guessed | | |
| Planted recurring found / missed | | |
| Planted one-offs flagged / false alarms | | |
| API calls on first run / second run | | 0 |

## Status
Parser, merchant extraction, rules, LLM layer, recurring and unusual detection are unit-tested (`tests/`). The Streamlit UI and the real
LLM call were written without the real sample file, the answer key, or a live API key, so run them once and fix anything that differs.
