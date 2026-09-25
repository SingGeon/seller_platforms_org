"""sellers.password_hash -> sellers.password (passwords stored in plain text, team decision)

Existing PBKDF2 values stay in the column and are replaced by the plain text at the next successful login.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25 23:30:00
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('sellers', 'password_hash', new_column_name='password')


def downgrade() -> None:
    op.alter_column('sellers', 'password', new_column_name='password_hash')
