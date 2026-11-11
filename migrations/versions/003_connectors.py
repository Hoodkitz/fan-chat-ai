"""Per-tenant portal connector configuration (encrypted JSON).

Revision ID: 003
"""
from alembic import op

revision = "003"
down_revision = "002"


def upgrade():
    op.execute("ALTER TABLE creator_profiles ADD COLUMN IF NOT EXISTS connectors TEXT")


def downgrade():
    op.execute("ALTER TABLE creator_profiles DROP COLUMN IF EXISTS connectors")
