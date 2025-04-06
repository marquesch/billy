"""Added billy mood column to user table

Revision ID: 7b48e3d94f19
Revises: 975eeba8a9f1
Create Date: 2025-04-06 03:42:59.627552

"""

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7b48e3d94f19"
down_revision: Union[str, None] = "975eeba8a9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    billy_mood_enum = sa.Enum(
        "NEUTRAL", "SARCASTIC", "GRUMPY", "HAPPY", "SAD", name="billymood"
    )

    billy_mood_enum.create(op.get_bind())

    op.add_column(
        "user_account",
        sa.Column(
            "billy_mood",
            billy_mood_enum,
            server_default="NEUTRAL",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_account", "billy_mood")
