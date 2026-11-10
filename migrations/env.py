import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alembic import context  # noqa: E402
from sqlalchemy import create_engine, pool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.domain import models  # noqa: E402,F401

engine = create_engine(settings.MIGRATION_DATABASE_URL, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=models.Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
