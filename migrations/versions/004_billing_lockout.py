"""Billing (plan, trial, Stripe customer, processed Stripe events) and login lockout.

Revision ID: 004
"""
from alembic import op

revision = "004"
down_revision = "003"
APP = "fanchat_app"


def upgrade():
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan VARCHAR(20) NOT NULL DEFAULT 'trial'")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ DEFAULT now() + interval '14 days'")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tenants_stripe_customer_id ON tenants (stripe_customer_id)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_logins INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ")
    op.execute("CREATE TABLE IF NOT EXISTS stripe_events (event_id VARCHAR(100) PRIMARY KEY, "
               "received_at TIMESTAMPTZ DEFAULT now())")
    op.execute(f"GRANT SELECT, INSERT ON stripe_events TO {APP}")


def downgrade():
    op.execute("DROP TABLE IF EXISTS stripe_events")
    for col in ("locked_until", "failed_logins"):
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col}")
    for col in ("stripe_customer_id", "trial_ends_at", "plan"):
        op.execute(f"ALTER TABLE tenants DROP COLUMN IF EXISTS {col}")
