"""scoring_config.deal_model: admin overrides of the deal (value / cost / profit) estimate assumptions

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26 22:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scoring_config', sa.Column('deal_model', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    op.drop_column('scoring_config', 'deal_model')
