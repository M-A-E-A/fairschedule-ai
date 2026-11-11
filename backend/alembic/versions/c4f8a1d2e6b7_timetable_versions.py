"""timetable publish versions (S-06)

Revision ID: c4f8a1d2e6b7
Revises: a1c4e7f9d2b3
Create Date: 2026-11-11 16:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4f8a1d2e6b7'
down_revision: str | Sequence[str] | None = 'a1c4e7f9d2b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'timetableversion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('institution_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('label', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('published_by_email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=False),
        sa.Column('json_payload', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('timetableversion', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_timetableversion_institution_id'), ['institution_id'], unique=False
        )
        batch_op.create_index(
            'uq_timetableversion_inst_version', ['institution_id', 'version'], unique=True
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('timetableversion', schema=None) as batch_op:
        batch_op.drop_index('uq_timetableversion_inst_version', batch_op.f('uq_timetableversion_inst_version'))
        batch_op.drop_index(
            batch_op.f('ix_timetableversion_institution_id'), batch_op.f('ix_timetableversion_institution_id')
        )
    op.drop_table('timetableversion')
