import json

from analyser.llm import categorise_pending, parse_response
from analyser.merchant import cache_key, extract_merchant
from analyser.rules import match_rule


def test_merchant_formats():
    assert extract_merchant("UPI-SWIGGY LIMITEDswiggy.upi@icici-UTIB0000456-986872774348-UPI") == "SWIGGY LIMITED"
    assert extract_merchant("POS 525293XXXXXX1234 AMAZON PAY INDIA POS DEBIT") == "AMAZON PAY INDIA"
    assert extract_merchant("NEFT CR-HDFC0000001-ACME CORP-SALARY") == "ACME CORP"
    assert extract_merchant("ACH D- HDFCMUTUALFUND-000123") == "HDFCMUTUALFUND"
    assert extract_merchant("BIL/BPAY/000123/BESCOM ELECTRICITY") == "BESCOM ELECTRICITY"
    assert extract_merchant("ATW-525293XXXXXX1234-HDFC BANK ATM") == "ATM CASH"
    assert extract_merchant("SMS ALERT CHARGES") == "SMS ALERT CHARGES"


def test_cache_key_masks_changing_ids():
    assert cache_key("PAYTMQR281005050101", "debit") == cache_key("PAYTMQR999999999999", "debit")


def test_longest_keyword_wins_and_tie_goes_to_first():
    rules = [{"keyword": "reliance", "category": "Shopping"}, {"keyword": "reliance jio", "category": "Utilities & Bills"}]
    assert match_rule("UPI-RELIANCE JIO-X", rules) == 1
    tie = [{"keyword": "abc", "category": "Shopping"}, {"keyword": "ABC", "category": "Groceries"}]
    assert match_rule("xx abc", tie) == 0


def test_whole_word_avoids_substring_false_positive():
    rules = [{"keyword": "uber", "category": "Transport", "whole_word": True}]
    assert match_rule("UPI-SUBERBIA STORE", rules) is None
    assert match_rule("UPI-UBER INDIA-X", rules) == 0


def test_invalid_label_rejected_and_missing_item_retried_then_cached():
    calls = []

    def fake(system, user):
        calls.append(json.loads(user))
        if len(calls) == 1:   # first reply: bad label for id 0, id 1 missing
            return '[{"id":0,"category":"Banana","reason":"x"}]'
        return '[{"id":1,"category":"Pets","reason":"vet"}]'

    cache = {}
    stats = categorise_pending({"debit|A": ("a", "debit"), "debit|B": ("b", "debit")}, cache, fake)
    assert cache["debit|A"]["category"] == "Uncategorized" and cache["debit|B"]["category"] == "Pets"
    assert stats["api_calls"] == 2 and stats["rejected"] == 1
    assert all(set(p) == {"id", "narration", "direction"} for p in calls[0])   # nothing extra sent
    again = categorise_pending({"debit|A": ("a", "debit"), "debit|B": ("b", "debit")}, cache, fake)
    assert again["api_calls"] == 0          # everything cached, including the Uncategorized answer


def test_second_run_makes_zero_calls():
    cache = {"debit|A": {"category": "Pets", "reason": ""}}
    n = []
    stats = categorise_pending({"debit|A": ("a", "debit")}, cache, lambda s, u: n.append(1) or "[]")
    assert stats["api_calls"] == 0 and not n


def test_garbage_json_gives_uncategorized_not_crash():
    cache = {}
    stats = categorise_pending({"debit|A": ("a", "debit")}, cache, lambda s, u: "not json")
    assert cache == {} and stats["unanswered"] == 1 and stats["api_calls"] == 2


def test_parse_response_tolerates_code_fences():
    r, rej = parse_response('```json\n[{"id":0,"category":"Pets","reason":"vet"}]\n```')
    assert r[0]["category"] == "Pets" and rej == 0
