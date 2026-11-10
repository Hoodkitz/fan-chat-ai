"""Baseline: schema, non-privileged app role, FORCE RLS.

Revision ID: 001
"""
from alembic import op
from sqlalchemy import text

from app.core.config import settings
from app.domain.models import TENANT_TABLES, Base

revision = "001"
down_revision = None
APP = "fanchat_app"


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    pw = settings.APP_DB_PASSWORD.replace("'", "''")
    if bind.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": APP}).scalar():
        op.execute(f"ALTER ROLE {APP} LOGIN PASSWORD '{pw}' NOSUPERUSER NOBYPASSRLS")
    else:
        op.execute(f"CREATE ROLE {APP} LOGIN PASSWORD '{pw}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP}")
    op.execute("CREATE OR REPLACE FUNCTION app_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS "
               "$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$")
    op.execute("CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS "
               "$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$")
    for t in TENANT_TABLES + ["tenants", "memberships"]:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    for t in TENANT_TABLES:
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = app_tenant_id()) "
                   "WITH CHECK (tenant_id = app_tenant_id())")
    op.execute("CREATE POLICY m_read ON memberships FOR SELECT USING (tenant_id = app_tenant_id() OR user_id = app_user_id())")
    op.execute("CREATE POLICY m_write ON memberships FOR ALL USING (tenant_id = app_tenant_id()) "
               "WITH CHECK (tenant_id = app_tenant_id())")
    op.execute("CREATE POLICY t_all ON tenants FOR ALL USING (id = app_tenant_id()) WITH CHECK (id = app_tenant_id())")


def downgrade():
    Base.metadata.drop_all(op.get_bind())
