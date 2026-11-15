from datetime import date

import httpx
import respx

from eventalpha.sec import client as sec_client
from eventalpha.sec import events, form4, form13f, periodic
from eventalpha.sec.index import IndexEntry, daily_index_url, parse_daily_index, select_filings
from eventalpha.sec.submission import parse_submission

INDEX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type

Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
1-A POS          Doroni Aerospace, Inc.                                        1890225     20261113    edgar/data/1890225/0001683168-26-008661.txt
8-K              AAON, INC.                                                    824142      20261113    edgar/data/824142/0001628280-26-073758.txt
8-K              AAON, INC.                                                    824142      20261113    edgar/data/824142/0001628280-26-073758.txt
SCHEDULE 13D     NEW ENTERPRISE ASSOCIATES 13 LP                               1452907     20261113    edgar/data/1452907/0001072613-26-000890.txt
SCHEDULE 13D     Coursera, Inc.                                                1651562     20261113    edgar/data/1651562/0001072613-26-000890.txt
13F-HR           1060 Capital, LLC                                             1602119     20261113    edgar/data/1602119/0001602119-26-000005.txt
"""


def entry(form: str, cik: str = "824142", acc: str = "0001628280-26-073758") -> IndexEntry:
    return IndexEntry(form, "AAON, INC.", cik, date(2026, 11, 13), f"edgar/data/{cik}/{acc}.txt")


def submission(header_extra: str, docs: str) -> str:
    return (
        "<SEC-HEADER>\n<ACCEPTANCE-DATETIME>20261113151630\nACCESSION NUMBER:\t0001628280-26-073758\n"
        f"CONFORMED PERIOD OF REPORT:\t20260930\n{header_extra}</SEC-HEADER>\n{docs}"
    )


def doc(doc_type: str, body: str, description: str = "") -> str:
    return (
        f"<DOCUMENT>\n<TYPE>{doc_type}\n<FILENAME>f\n<DESCRIPTION>{description}\n<TEXT>\n{body}\n</TEXT>\n</DOCUMENT>\n"
    )


# ---------- index ----------


def test_index_url_uses_quarter():
    assert daily_index_url(date(2026, 11, 13)).endswith("/2026/QTR4/form.20261113.idx")
    assert "/QTR1/" in daily_index_url(date(2026, 3, 31))


def test_parse_index_handles_multiword_form_types():
    entries = parse_daily_index(INDEX)
    assert [e.form_type for e in entries][:2] == ["1-A POS", "8-K"]
    assert entries[3].form_type == "SCHEDULE 13D"


def test_select_dedupes_and_prefers_universe_party():
    entries = parse_daily_index(INDEX)
    forms = frozenset({"8-K", "SCHEDULE 13D"})
    selected = select_filings(entries, forms, universe_ciks={"824142", "1651562"})
    assert [(e.form_type, e.cik) for e in selected] == [("8-K", "824142"), ("SCHEDULE 13D", "1651562")]
    # 13F filers are funds, never in the issuer universe: no filter
    assert len(select_filings(entries, frozenset({"13F-HR"}), None)) == 1


# ---------- 8-K ----------


def test_8k_article():
    text = submission(
        "ITEM INFORMATION:\tResults of Operations and Financial Condition\n"
        "ITEM INFORMATION:\tMaterial Modifications to Rights of Security Holders\n"
        "ITEM INFORMATION:\tFinancial Statements and Exhibits\n",
        doc("8-K", "<p>Cover page</p>")
        + doc("EX-99.1", "<p>AAON reports <b>record</b> revenue</p><script>x()</script>")
        + doc("EX-10.1", "loan agreement"),
    )
    sub = parse_submission(text)
    assert sub.accepted_at.isoformat() == "2026-11-13T15:16:30-05:00"
    a = events.to_article(entry("8-K"), sub, {"824142": ("AAON, INC.", ["AAON"])})
    assert a.form_type == "8-K" and a.tickers == ["AAON"]
    assert a.sec_items == ["2.02", "3.03", "9.01"]
    assert a.body == "AAON reports\nrecord\nrevenue"  # press release only, script stripped
    assert "Financial Statements" not in a.title


# ---------- 13D ----------

D13 = """<XML>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D"><formData>
<coverPageHeader><issuerInfo><issuerCIK>0001651562</issuerCIK><issuerName>Coursera, Inc.</issuerName></issuerInfo>
</coverPageHeader>
<reportingPersons><reportingPersonInfo><reportingPersonName>NEA 13, L.P.</reportingPersonName>
<percentOfClass>5.1</percentOfClass></reportingPersonInfo></reportingPersons>
<items1To7><item4><transactionPurpose>Seek board representation.</transactionPurpose></item4></items1To7>
</formData></edgarSubmission>
</XML>"""


def test_13d_article_uses_issuer_from_xml():
    sub = parse_submission(submission("", doc("SCHEDULE 13D", D13)))
    e = entry("SCHEDULE 13D", cik="1452907")  # index line of the *filer*
    a = events.to_article(e, sub, {"1651562": ("Coursera, Inc.", ["COUR"])})
    assert a.cik == "1651562" and a.tickers == ["COUR"]
    assert a.title == "NEA 13, L.P. discloses a 5.1% stake in Coursera, Inc. (Schedule 13D)"
    assert "Purpose of transaction: Seek board representation." in a.body
    assert events.to_article(e, sub, {}) is None  # issuer not listed


# ---------- Form 4 ----------

F4 = """<XML>
<ownershipDocument>
<issuer><issuerCik>0000824142</issuerCik><issuerName>AAON</issuerName><issuerTradingSymbol>aaon</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0000000001</rptOwnerCik><rptOwnerName>Jane CEO</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>true</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<securityTitle><value>Common</value></securityTitle><transactionDate><value>2026-11-11</value></transactionDate>
<transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares>
<transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
</nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>
</XML>"""


def test_form4_rows():
    rows = form4.parse_form4(entry("4"), parse_submission(submission("", doc("4", F4))))
    assert len(rows) == 1
    r = rows[0]
    assert (r["issuer_cik"], r["ticker"], r["owner_name"], r["officer_title"]) == ("824142", "AAON", "Jane CEO", "CEO")
    assert r["is_director"] and r["is_officer"] and not r["is_ten_percent_owner"]
    assert (r["transaction_code"], int(r["shares"]), r["price"]) == ("P", 1000, None)  # footnoted price
    assert r["transaction_date"] == date(2026, 11, 11) and r["ownership"] == "D"


# ---------- 13F ----------

F13_PRIMARY = """<XML><edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><formData>
<coverPage><reportCalendarOrQuarter>09-30-2026</reportCalendarOrQuarter></coverPage>
<summaryPage><tableEntryTotal>1</tableEntryTotal><tableValueTotal>5215950</tableValueTotal></summaryPage>
</formData><headerData><filerInfo><periodOfReport>09-30-2026</periodOfReport></filerInfo></headerData></edgarSubmission></XML>"""
F13_TABLE = """<XML><ns1:informationTable xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<ns1:infoTable><ns1:nameOfIssuer>GRANITE CONSTR INC</ns1:nameOfIssuer><ns1:titleOfClass>COM</ns1:titleOfClass>
<ns1:cusip>387328107</ns1:cusip><ns1:value>5215950</ns1:value>
<ns1:shrsOrPrnAmt><ns1:sshPrnamt>45000</ns1:sshPrnamt><ns1:sshPrnamtType>SH</ns1:sshPrnamtType></ns1:shrsOrPrnAmt>
<ns1:investmentDiscretion>SOLE</ns1:investmentDiscretion>
<ns1:votingAuthority><ns1:Sole>45000</ns1:Sole><ns1:Shared>0</ns1:Shared><ns1:None>0</ns1:None></ns1:votingAuthority>
</ns1:infoTable></ns1:informationTable></XML>"""


def test_13f_header_and_holdings():
    sub = parse_submission(submission("", doc("13F-HR", F13_PRIMARY) + doc("INFORMATION TABLE", F13_TABLE)))
    header, rows = form13f.parse_13f(entry("13F-HR", cik="1602119"), sub)
    assert header["period_of_report"] == date(2026, 9, 30) and int(header["table_entry_total"]) == 1
    assert len(rows) == 1
    assert (rows[0]["cusip"], int(rows[0]["shares"]), rows[0]["share_type"], int(rows[0]["voting_sole"])) == (
        "387328107",
        45000,
        "SH",
        45000,
    )


# ---------- 10-Q / 10-K ----------


def test_sections_skip_table_of_contents():
    body = "risk text. " * 40
    mdna = "We grew revenue. " * 40
    text = (
        "Item 1A. Risk Factors 12\nItem 2. Management's Discussion 20\n"  # table of contents
        f"Item 2. Management's Discussion and Analysis\n{mdna}\n"
        "Item 3. Quantitative and Qualitative Disclosures\nsmall\n"
        f"Item 1A. Risk Factors\n{body}\nItem 2. Unregistered Sales of Equity Securities\nnone\n"
    )
    sections = periodic.extract_sections("10-Q", text)
    assert sections["mdna"].startswith("Item 2. Management's Discussion and Analysis\nWe grew")
    assert sections["risk_factors"].startswith("Item 1A. Risk Factors\nrisk text.")
    assert "Unregistered" not in sections["risk_factors"]


def test_company_facts_keep_only_this_filing(monkeypatch):
    monkeypatch.setattr(sec_client.time, "sleep", lambda s: None)
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-07-01",
                                "end": "2026-09-30",
                                "val": 100,
                                "accn": "0001628280-26-073758",
                                "fy": 2026,
                                "fp": "Q3",
                                "form": "10-Q",
                            },
                            {
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "val": 90,
                                "accn": "0000000000-25-000001",
                                "fy": 2025,
                                "fp": "Q3",
                                "form": "10-Q",
                            },
                        ]
                    }
                }
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [{"end": "2026-10-31", "val": 81_000_000, "accn": "0001628280-26-073758"}]}
                }
            },
        }
    }
    with respx.mock:
        respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000824142.json").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with sec_client.RateLimitedClient("t", 1000) as c:
            rows = periodic.fetch_fact_rows(c, entry("10-Q"))
    assert {(r["concept"], int(r["value"]), r["period_start"]) for r in rows} == {
        ("us-gaap:Revenues", 100, date(2026, 7, 1)),
        ("dei:EntityCommonStockSharesOutstanding", 81_000_000, None),
    }


def test_stream_retries_transient_errors(monkeypatch):
    monkeypatch.setattr(sec_client.time, "sleep", lambda s: None)
    with respx.mock:
        route = respx.get("https://www.sec.gov/x.txt").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, text="a\nb")]
        )
        with sec_client.RateLimitedClient("test agent", requests_per_second=1000) as c:
            assert list(c.stream_lines("https://www.sec.gov/x.txt")) == ["a", "b"]
        assert route.call_count == 2


def test_cross_references_do_not_end_a_section():
    text = (
        "Item 2. Management's Discussion and Analysis\n"
        + "Revenue grew, as described in Item 1A. Risk Factors of our 10-K, and more. " * 10
        + "\nItem 3. Quantitative and Qualitative Disclosures\n"
    )
    assert "and more." in periodic.extract_sections("10-Q", text)["mdna"][-20:]


def test_6k_generic_exhibit_label_uses_press_release_headline():
    text = submission(
        "",
        doc("6-K", "<p>cover</p>")
        + doc(
            "EX-99.1",
            "<p>EXHIBIT 99.1</p><p>Americas Gold and Silver Reports Record Q3 Revenue</p>",
            description="EXHIBIT 99.1",
        ),
    )
    a = events.to_article(entry("6-K", cik="1"), parse_submission(text), {"1": ("Americas Gold", ["USAS"])})
    assert a.title == "AAON, INC. 6-K: Americas Gold and Silver Reports Record Q3 Revenue"
