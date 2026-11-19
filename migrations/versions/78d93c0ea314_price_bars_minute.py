"""Store first observations of completed one-minute candles."""

import sqlalchemy as sa
from alembic import op

revision = "78d93c0ea314"
down_revision = "f8b35af44a10"


def upgrade() -> None:
    op.create_table(
        "price_bars_minute",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.statement_timestamp(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("price_bars_minute")
