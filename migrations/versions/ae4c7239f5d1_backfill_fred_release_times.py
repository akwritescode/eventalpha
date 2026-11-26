"""Backfill standard Eastern release times for legacy FRED calendar rows."""

from alembic import op

revision = "ae4c7239f5d1"
down_revision = "d2f4a6b8c0e1"


def upgrade() -> None:
    # Snapshot the same release schedule used by fred_event_rows when this migration was written.
    op.execute("""
        UPDATE econ_events AS event
        SET scheduled_at = (event.event_date + schedule.release_time) AT TIME ZONE 'America/New_York'
        FROM (VALUES
            ('Gross Domestic Product', TIME '08:30'),
            ('Personal Income and Outlays', TIME '08:30'),
            ('Advance Monthly Sales for Retail and Food Services', TIME '08:30'),
            ('Unemployment Insurance Weekly Claims Report', TIME '08:30'),
            ('New Residential Construction', TIME '08:30'),
            ('Industrial Production and Capacity Utilization', TIME '09:15'),
            ('Surveys of Consumers', TIME '10:00'),
            ('Manufacturers'' Shipments, Inventories, and Orders', TIME '10:00'),
            ('ADP National Employment Report', TIME '08:15')
        ) AS schedule(title, release_time)
        WHERE event.source = 'fred' AND event.scheduled_at IS NULL AND event.title = schedule.title
    """)


def downgrade() -> None:
    # The previous schema accepts these timestamps. Clearing them could erase subsequent updates.
    pass
