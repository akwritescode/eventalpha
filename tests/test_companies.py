from eventalpha.companies import CompanyMatcher, merge_tickers, normalize_name

UNIVERSE = [
    {"ticker": "AAPL", "cik": "320193", "name": "Apple Inc.", "size_rank": 1},
    {"ticker": "LLY", "cik": "59478", "name": "ELI LILLY & Co", "size_rank": 9},
    {"ticker": "UBER", "cik": "1543151", "name": "Uber Technologies, Inc", "size_rank": 110},
    {"ticker": "TGT", "cik": "27419", "name": "TARGET CORP", "size_rank": 247},
    {"ticker": "NDAQ", "cik": "1120193", "name": "NASDAQ, INC.", "size_rank": 300},
    {"ticker": "AXP", "cik": "4962", "name": "AMERICAN EXPRESS CO", "size_rank": 60},
    {"ticker": "GOOGL", "cik": "1652044", "name": "Alphabet Inc.", "size_rank": 4},
    {"ticker": "GOOG", "cik": "1652044", "name": "Alphabet Inc.", "size_rank": 6},
    {"ticker": "TINY", "cik": "1", "name": "Tinyco Technologies Inc", "size_rank": 3500},
]
ALIASES = {"LLY": ["Lilly"], "AAPL": ["Apple"], "GOOGL": ["Google"]}
M = CompanyMatcher.build(UNIVERSE, ALIASES)


def test_sec_names_become_the_names_people_write():
    assert normalize_name("ELI LILLY & Co") == "Eli Lilly"
    assert normalize_name("Uber Technologies, Inc") == "Uber Technologies"
    assert normalize_name("AMERICAN EXPRESS CO") == "American Express"


def test_the_two_reported_headlines_get_their_tickers():
    assert M.find("Lilly to present new data across Zepbound at ObesityWeek 2026") == ["LLY"]
    assert M.find("Uber Data Breach Investigation: Edelson Lechtzin LLP Probes Class Action Claims") == ["UBER"]


def test_full_names_any_case_short_names_only_capitalised():
    assert M.find("enforcement action against AMERICAN EXPRESS COMPANY") == ["AXP"]
    assert M.find("uber eats a sandwich") == []
    assert M.find("Apple unveils a phone") == ["AAPL"] and M.find("apple harvest") == []


def test_everyday_words_exchanges_and_small_companies_are_not_matched():
    assert M.find("Target audience grows as company lists on Nasdaq") == []
    assert M.find("Tinyco Technologies announces results") == ["TINY"]  # full name: fine
    assert M.find("Tinyco announces results") == []  # short name of a small company: too risky


def test_one_ticker_per_company_largest_first_and_cited_tickers_lead():
    assert M.find("Google and Uber partner") == ["GOOGL", "UBER"]
    assert merge_tickers(["WWB"], ["UBER", "WWB"]) == ["WWB", "UBER"]
