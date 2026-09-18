"""create initial tables

Revision ID: 6efc54ea105e
Revises:
Create Date: 2026-09-12 23:22:14.049828

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6efc54ea105e"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open("metering/schema.sql") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE daily_rollups, hourly_rollups, events")
