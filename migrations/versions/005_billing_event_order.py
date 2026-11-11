"""Ignore out-of-order Stripe subscription events.

Revision ID: 005
"""
from alembic import op

revision = "005"
down_revision = "004"


def upgrade():
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_event_at BIGINT")


def downgrade():
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS billing_event_at")
