BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> e6fd1042f7a3

CREATE TABLE articles (
    id BIGSERIAL NOT NULL, 
    source VARCHAR(64) NOT NULL, 
    source_id TEXT NOT NULL, 
    form_type VARCHAR(20), 
    url TEXT NOT NULL, 
    title TEXT NOT NULL, 
    summary TEXT, 
    body TEXT, 
    company TEXT, 
    cik VARCHAR(10), 
    tickers VARCHAR(16)[] DEFAULT '{}' NOT NULL, 
    sec_items VARCHAR(8)[] DEFAULT '{}' NOT NULL, 
    published_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_articles_source_source_id UNIQUE (source, source_id)
);

CREATE INDEX ix_articles_cik ON articles (cik);

CREATE INDEX ix_articles_published_at ON articles (published_at);

CREATE INDEX ix_articles_tickers ON articles USING gin (tickers);

CREATE TABLE feed_state (
    feed_url TEXT NOT NULL, 
    etag TEXT, 
    last_modified TEXT, 
    last_status INTEGER, 
    last_fetched_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (feed_url)
);

CREATE TABLE financial_facts (
    id BIGSERIAL NOT NULL, 
    accession VARCHAR(25) NOT NULL, 
    cik VARCHAR(10) NOT NULL, 
    concept VARCHAR(96) NOT NULL, 
    unit VARCHAR(24) NOT NULL, 
    period_start DATE, 
    period_end DATE NOT NULL, 
    value NUMERIC(28, 6) NOT NULL, 
    fiscal_year INTEGER, 
    fiscal_period VARCHAR(4), 
    form_type VARCHAR(8), 
    frame VARCHAR(16), 
    PRIMARY KEY (id), 
    CONSTRAINT uq_financial_facts_fact UNIQUE NULLS NOT DISTINCT (accession, concept, unit, period_start, period_end)
);

CREATE INDEX ix_financial_facts_cik_concept ON financial_facts (cik, concept, period_end);

CREATE TABLE insider_transactions (
    accession VARCHAR(25) NOT NULL, 
    row_no INTEGER NOT NULL, 
    form_type VARCHAR(8) NOT NULL, 
    issuer_cik VARCHAR(10) NOT NULL, 
    ticker VARCHAR(16), 
    issuer_name TEXT, 
    owner_cik VARCHAR(10), 
    owner_name TEXT, 
    owner_count INTEGER NOT NULL, 
    is_director BOOLEAN NOT NULL, 
    is_officer BOOLEAN NOT NULL, 
    is_ten_percent_owner BOOLEAN NOT NULL, 
    officer_title TEXT, 
    is_derivative BOOLEAN NOT NULL, 
    security_title TEXT, 
    transaction_date DATE, 
    transaction_code VARCHAR(2), 
    shares NUMERIC(24, 6), 
    price NUMERIC(18, 6), 
    acquired_disposed VARCHAR(1), 
    shares_owned_after NUMERIC(24, 6), 
    ownership VARCHAR(1), 
    filed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (accession, row_no)
);

CREATE INDEX ix_insider_code_date ON insider_transactions (transaction_code, transaction_date);

CREATE INDEX ix_insider_ticker_date ON insider_transactions (ticker, transaction_date);

CREATE TABLE institutional_filings (
    accession VARCHAR(25) NOT NULL, 
    form_type VARCHAR(10) NOT NULL, 
    filer_cik VARCHAR(10) NOT NULL, 
    filer_name TEXT NOT NULL, 
    period_of_report DATE, 
    amendment_type VARCHAR(20), 
    table_entry_total NUMERIC(12, 0), 
    table_value_total NUMERIC(24, 0), 
    PRIMARY KEY (accession)
);

CREATE INDEX ix_institutional_filings_filer_cik ON institutional_filings (filer_cik);

CREATE INDEX ix_institutional_filings_period_of_report ON institutional_filings (period_of_report);

CREATE TABLE report_sections (
    accession VARCHAR(25) NOT NULL, 
    section VARCHAR(32) NOT NULL, 
    cik VARCHAR(10) NOT NULL, 
    form_type VARCHAR(8) NOT NULL, 
    period_of_report DATE, 
    text TEXT NOT NULL, 
    chars INTEGER NOT NULL, 
    PRIMARY KEY (accession, section)
);

CREATE INDEX ix_report_sections_cik_period ON report_sections (cik, period_of_report);

CREATE TABLE sec_filings (
    accession VARCHAR(25) NOT NULL, 
    family VARCHAR(16) NOT NULL, 
    form_type VARCHAR(20) NOT NULL, 
    cik VARCHAR(10) NOT NULL, 
    company TEXT NOT NULL, 
    date_filed DATE NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    rows INTEGER DEFAULT '0' NOT NULL, 
    detail TEXT, 
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (accession)
);

CREATE INDEX ix_sec_filings_date_family ON sec_filings (date_filed, family);

CREATE TABLE ticker_universe (
    ticker VARCHAR(16) NOT NULL, 
    cik VARCHAR(10) NOT NULL, 
    name TEXT NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (ticker)
);

CREATE INDEX ix_ticker_universe_cik ON ticker_universe (cik);

CREATE TABLE article_scores (
    article_id BIGINT NOT NULL, 
    model VARCHAR(32) NOT NULL, 
    questions_version VARCHAR(16) NOT NULL, 
    sentiment VARCHAR(16) NOT NULL, 
    p_bullish FLOAT NOT NULL, 
    p_bearish FLOAT NOT NULL, 
    p_neutral FLOAT NOT NULL, 
    sentiment_score FLOAT NOT NULL, 
    sentiment_confidence FLOAT NOT NULL, 
    materiality FLOAT NOT NULL, 
    materiality_confidence FLOAT NOT NULL, 
    company_specific FLOAT NOT NULL, 
    events JSONB NOT NULL, 
    input_tokens INTEGER, 
    scored_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (article_id, model, questions_version), 
    FOREIGN KEY(article_id) REFERENCES articles (id) ON DELETE CASCADE
);

CREATE TABLE institutional_holdings (
    accession VARCHAR(25) NOT NULL, 
    row_no INTEGER NOT NULL, 
    cusip VARCHAR(9) NOT NULL, 
    issuer_name TEXT, 
    title_of_class TEXT, 
    value_usd NUMERIC(24, 0), 
    shares NUMERIC(24, 0), 
    share_type VARCHAR(4), 
    put_call VARCHAR(4), 
    investment_discretion VARCHAR(8), 
    voting_sole NUMERIC(24, 0), 
    voting_shared NUMERIC(24, 0), 
    voting_none NUMERIC(24, 0), 
    PRIMARY KEY (accession, row_no), 
    FOREIGN KEY(accession) REFERENCES institutional_filings (accession) ON DELETE CASCADE
);

CREATE INDEX ix_holdings_cusip ON institutional_holdings (cusip);

INSERT INTO alembic_version (version_num) VALUES ('e6fd1042f7a3') RETURNING alembic_version.version_num;

COMMIT;

