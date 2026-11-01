"""Original schema frozen so future models cannot alter migration 001."""
from alembic import op
import sqlalchemy as sa
revision = '001'
down_revision = None


def upgrade():
    op.create_table('users', sa.Column('id', sa.String(), primary_key=True), sa.Column('org', sa.String(), nullable=False), sa.Column('email', sa.String(), nullable=False, unique=True), sa.Column('password', sa.Text(), nullable=False), sa.Column('role', sa.String(), nullable=False), sa.Column('totp', sa.String(), nullable=True))
    op.create_index('ix_users_org', 'users', ['org'])
    op.create_table('sessions', sa.Column('token', sa.String(), primary_key=True), sa.Column('user_id', sa.String(), nullable=False), sa.Column('expires', sa.String(), nullable=False))
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_table('records', sa.Column('id', sa.String(), primary_key=True), sa.Column('org', sa.String(), nullable=False), sa.Column('kind', sa.String(), nullable=False), sa.Column('external_id', sa.String(), nullable=False), sa.Column('data', sa.JSON(), nullable=False), sa.Column('created', sa.String(), nullable=False), sa.UniqueConstraint('org', 'kind', 'external_id'))
    op.create_index('ix_records_org', 'records', ['org'])
    op.create_index('ix_records_kind', 'records', ['kind'])


def downgrade():
    for table in ['records', 'sessions', 'users']:
        op.drop_table(table)
