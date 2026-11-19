"""Preserve existing grants and prepare action-aware resource authorization.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Prior authorization ignored grants.action, so existing rows must retain their former
    # resource-wide behavior. New grants use explicit action values through the API.
    op.execute("UPDATE grants SET action = '*'")

    # Existing local Tool grants can be mapped to stable IDs. Other name-based grants remain
    # usable through the framework's legacy-name fallback, including versioned Skills.
    op.execute(
        """
        UPDATE grants
        SET resource_id = tools.id
        FROM tools
        WHERE grants.tenant_id = tools.tenant_id
          AND grants.resource_type = 'tool'
          AND grants.resource_id = tools.name
          AND (
              SELECT count(*)
              FROM tools AS matching_tools
              WHERE matching_tools.tenant_id = grants.tenant_id
                AND matching_tools.name = grants.resource_id
          ) = 1
        """
    )


def downgrade() -> None:
    # Restore name-based references for local Tools before reverting wildcard grants.
    op.execute(
        """
        UPDATE grants
        SET resource_id = tools.name
        FROM tools
        WHERE grants.tenant_id = tools.tenant_id
          AND grants.resource_type = 'tool'
          AND grants.resource_id = tools.id
        """
    )
    op.execute("UPDATE grants SET action = 'execute' WHERE action = '*'")
