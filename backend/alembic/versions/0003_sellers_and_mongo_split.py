"""seller accounts; companies, documents, signals, events, scores, runs and LLM cache move to MongoDB

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25 22:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    # These now live in MongoDB (see app/mongo.py). Children first because of the foreign keys.
    for table in ('signals', 'lead_scores', 'company_events', 'raw_documents', 'llm_cache', 'pipeline_runs', 'companies'):
        op.drop_table(table)

    op.create_table('sellers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=300), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sellers_email'), 'sellers', ['email'], unique=True)
    op.create_table('seller_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_seller_sessions_seller_id'), 'seller_sessions', ['seller_id'], unique=False)
    op.create_table('lead_assignments',
    sa.Column('company_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=True),
    sa.Column('stage', sa.String(length=20), nullable=False),
    sa.Column('notes', JSON, nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('company_id')
    )
    op.create_index(op.f('ix_lead_assignments_seller_id'), 'lead_assignments', ['seller_id'], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Company data lives in MongoDB since 0003; restore from a backup to go back.")
