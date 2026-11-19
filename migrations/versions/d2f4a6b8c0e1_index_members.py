"""Rename minute_universe_members to index_members: one membership list for every consumer.

The S&P 500 / Nasdaq-100 membership started as the candle collector's universe. Earnings dates
and index alerts now read it too, and it gains the Dow Jones Industrial Average, so the table is
named for what it holds. Rows are a mirror of config/index_members.json, rewritten on load.
"""

from alembic import op

revision = "d2f4a6b8c0e1"
down_revision = "b6a729ce18f0"


def upgrade() -> None:
    op.rename_table("minute_universe_members", "index_members")
    op.execute("ALTER TABLE index_members RENAME CONSTRAINT minute_universe_members_pkey TO index_members_pkey")


def downgrade() -> None:
    op.execute("ALTER TABLE index_members RENAME CONSTRAINT index_members_pkey TO minute_universe_members_pkey")
    op.rename_table("index_members", "minute_universe_members")
