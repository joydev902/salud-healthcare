"""queue search indexes: trigram member search, covering initiative probe

Revision ID: c41f0a7d2e13
Revises: 99b92bfb8d68
Create Date: 2026-10-20 01:10:00

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'c41f0a7d2e13'
down_revision: str | None = '99b92bfb8d68'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pg_trgm is a trusted extension (PG13+), so the database owner can create it.
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_index(
        'ix_members_name_trgm', 'members', ['member_name'],
        postgresql_using='gin', postgresql_ops={'member_name': 'gin_trgm_ops'},
    )
    op.create_index(
        'ix_members_external_id_trgm', 'members', ['external_member_id'],
        postgresql_using='gin', postgresql_ops={'external_member_id': 'gin_trgm_ops'},
    )
    # (opportunity_id, initiative) makes the initiative EXISTS probe index-only and
    # supersedes the single-column opportunity_id index.
    op.create_index(
        'ix_source_opportunity_initiative', 'source_records', ['opportunity_id', 'initiative']
    )
    op.drop_index('ix_source_records_opportunity_id', table_name='source_records')


def downgrade() -> None:
    op.create_index(
        'ix_source_records_opportunity_id', 'source_records', ['opportunity_id'], unique=False
    )
    op.drop_index('ix_source_opportunity_initiative', table_name='source_records')
    op.drop_index('ix_members_external_id_trgm', table_name='members')
    op.drop_index('ix_members_name_trgm', table_name='members')
