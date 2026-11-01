"""Operational persistence with explicit, versioned table definitions."""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'


def upgrade():
    op.create_table('organizations', sa.Column('id', sa.String(), primary_key=True), sa.Column('name', sa.String(), nullable=False), sa.Column('settings', sa.JSON(), nullable=False), sa.Column('created', sa.String(), nullable=False))
    op.create_table('integration_credentials', sa.Column('id', sa.String(), primary_key=True), sa.Column('org', sa.String(), nullable=False), sa.Column('provider', sa.String(), nullable=False), sa.Column('ciphertext', sa.Text(), nullable=False), sa.Column('updated', sa.String(), nullable=False), sa.UniqueConstraint('org', 'provider'))
    op.create_index('ix_integration_credentials_org', 'integration_credentials', ['org'])
    op.create_table('source_sync_jobs', sa.Column('id', sa.String(), primary_key=True), sa.Column('org', sa.String(), nullable=False), sa.Column('source', sa.String(), nullable=False), sa.Column('window', sa.String(), nullable=False), sa.Column('state', sa.String(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False), sa.Column('checkpoint', sa.JSON(), nullable=False), sa.Column('error', sa.String(), nullable=True), sa.Column('updated', sa.String(), nullable=False), sa.UniqueConstraint('org', 'source', 'window'))
    op.create_index('ix_source_sync_jobs_org', 'source_sync_jobs', ['org'])
    op.create_table('investigation_attachments', sa.Column('id', sa.String(), primary_key=True), sa.Column('org', sa.String(), nullable=False), sa.Column('case_id', sa.String(), nullable=False), sa.Column('name', sa.String(), nullable=False), sa.Column('media_type', sa.String(), nullable=False), sa.Column('ciphertext', sa.Text(), nullable=False), sa.Column('digest', sa.String(), nullable=False), sa.Column('created', sa.String(), nullable=False))
    op.create_index('ix_investigation_attachments_org', 'investigation_attachments', ['org'])
    op.create_index('ix_investigation_attachments_case_id', 'investigation_attachments', ['case_id'])


def downgrade():
    for table in ['investigation_attachments', 'source_sync_jobs', 'integration_credentials', 'organizations']:
        op.drop_table(table)
