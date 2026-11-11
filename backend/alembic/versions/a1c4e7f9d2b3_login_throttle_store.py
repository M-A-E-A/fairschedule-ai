"""login attempt store for persistent login throttling (S-02)

Revision ID: a1c4e7f9d2b3
Revises: 72bbb9943009
Create Date: 2026-11-11 16:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e7f9d2b3'
down_revision: str | Sequence[str] | None = '72bbb9943009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'loginattempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_ip', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('identifier', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('failed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('loginattempt', schema=None) as batch_op:
        batch_op.create_index('ix_loginattempt_key', ['client_ip', 'identifier'], unique=False)
        batch_op.create_index('ix_loginattempt_failed_at', ['failed_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('loginattempt', schema=None) as batch_op:
        batch_op.drop_index('ix_loginattempt_failed_at', batch_op.f('ix_loginattempt_failed_at'))
        batch_op.drop_index('ix_loginattempt_key', batch_op.f('ix_loginattempt_key'))
    op.drop_table('loginattempt')
