"""Partition minute candles by UTC day and preserve full OHLCV when available."""

import sqlalchemy as sa
from alembic import op

revision = "b6a729ce18f0"
down_revision = "78d93c0ea314"


def upgrade() -> None:
    op.create_table(
        "minute_universe_members",
        sa.Column("index_name", sa.String(16), primary_key=True),
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE price_bars_minute RENAME TO price_bars_minute_legacy")
    op.execute(
        "ALTER TABLE price_bars_minute_legacy RENAME CONSTRAINT price_bars_minute_pkey TO price_bars_minute_legacy_pkey"
    )
    op.create_table(
        "price_bars_minute",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column("high", sa.Numeric()),
        sa.Column("low", sa.Numeric()),
        sa.Column("volume", sa.BigInteger()),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.statement_timestamp()
        ),
        postgresql_partition_by="RANGE (started_at)",
    )
    op.execute("""
        DO $$
        DECLARE
            d date;
            first_day date;
            last_day date;
        BEGIN
            SELECT LEAST(COALESCE((min(started_at) AT TIME ZONE 'UTC')::date, current_date), current_date - 14),
                   GREATEST(COALESCE((max(started_at) AT TIME ZONE 'UTC')::date, current_date), current_date + 7)
            INTO first_day, last_day FROM price_bars_minute_legacy;
            d := first_day;
            WHILE d <= last_day LOOP
                EXECUTE format('CREATE TABLE %I PARTITION OF price_bars_minute FOR VALUES FROM (%L) TO (%L)',
                    'price_bars_minute_p' || to_char(d, 'YYYYMMDD'),
                    d::text || ' 00:00:00+00', (d + 1)::text || ' 00:00:00+00');
                d := d + 1;
            END LOOP;
        END $$;
    """)
    op.execute("""
        INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
        SELECT symbol, started_at, open, close, first_seen_at FROM price_bars_minute_legacy
    """)
    op.drop_table("price_bars_minute_legacy")
    # Backstop for unusual historical/manual loads. The collector pre-creates all its days.
    op.execute("CREATE TABLE price_bars_minute_default PARTITION OF price_bars_minute DEFAULT")


def downgrade() -> None:
    op.drop_table("minute_universe_members")
    op.execute("ALTER TABLE price_bars_minute RENAME TO price_bars_minute_partitioned")
    op.execute(
        "ALTER TABLE price_bars_minute_partitioned RENAME CONSTRAINT price_bars_minute_pkey TO price_bars_minute_partitioned_pkey"
    )
    op.create_table(
        "price_bars_minute",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.statement_timestamp()
        ),
    )
    op.execute("""
        INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
        SELECT symbol, started_at, open, close, first_seen_at FROM price_bars_minute_partitioned
    """)
    op.execute("DROP TABLE price_bars_minute_partitioned CASCADE")
