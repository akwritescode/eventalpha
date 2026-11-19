"""Store paraphrased X discovery leads outside the article pipeline."""

import sqlalchemy as sa
from alembic import op

revision = "f8b35af44a10"
down_revision = "c492226ac7ac"


def upgrade() -> None:
    op.create_table(
        "x_leads",
        sa.Column("post_id", sa.String(20), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("paraphrase", sa.String(280), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.statement_timestamp(), nullable=False
        ),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id", ondelete="CASCADE")),
        sa.Column("article_content_hash", sa.String(64)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(article_id IS NULL AND article_content_hash IS NULL AND verified_at IS NULL) OR "
            "(article_id IS NOT NULL AND article_content_hash IS NOT NULL AND verified_at IS NOT NULL "
            "AND verified_at >= first_seen_at)",
            name="ck_x_leads_verification",
        ),
    )
    op.create_index("ix_x_leads_ticker_published_at", "x_leads", ["ticker", "published_at"])
    op.create_index("ix_x_leads_article_id", "x_leads", ["article_id"])


def downgrade() -> None:
    op.drop_table("x_leads")
