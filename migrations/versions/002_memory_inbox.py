"""Long-term memory facts (hybrid search), webhook inbox, webhook secret.

Revision ID: 002
"""
from alembic import op
from sqlalchemy import text

from app.domain.models import Base

revision = "002"
down_revision = "001"
APP = "fanchat_app"
NEW_TABLES = ["memory_facts", "webhook_inbox"]


def upgrade():
    bind = op.get_bind()
    op.execute("ALTER TABLE creator_profiles ADD COLUMN IF NOT EXISTS webhook_secret TEXT")
    Base.metadata.create_all(bind, tables=[Base.metadata.tables[t] for t in NEW_TABLES])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP}")
    for t in NEW_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = app_tenant_id()) "
                   "WITH CHECK (tenant_id = app_tenant_id())")


def downgrade():
    for t in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("ALTER TABLE creator_profiles DROP COLUMN IF EXISTS webhook_secret")
