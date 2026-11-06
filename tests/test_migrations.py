from alembic.config import Config

from alembic import command


def test_alembic_migrations_apply_and_revert():
    """Verify that Alembic migrations can be rolled back to base and reapplied cleanly."""
    alembic_cfg = Config("alembic.ini")

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # Upgrade back to head
    command.upgrade(alembic_cfg, "head")

    # Verify that database schema is fully synchronized with models
    command.check(alembic_cfg)
