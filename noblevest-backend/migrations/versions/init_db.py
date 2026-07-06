"""
noble-migration

Revision ID: init_db
Revises:
Create Date: 2026-07-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'init_db'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('client_type', sa.String(length=50), nullable=True, server_default='trader'),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default=sa.text('FALSE')),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('TRUE')),
        sa.Column('kyc_status', sa.String(length=20), nullable=True, server_default='pending'),
        sa.Column('role', sa.String(length=20), nullable=True, server_default='user'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    # Positions
    op.create_table(
        'positions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('asset_class', sa.String(length=30), nullable=True, server_default='equity'),
        sa.Column('quantity', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('avg_cost', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=True, server_default='USD'),
        sa.Column('exchange', sa.String(length=50), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_positions_user_id', 'positions', ['user_id'], unique=False)

    # Transactions
    op.create_table(
        'transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('position_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('total', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('fees', sa.Numeric(precision=10, scale=4), nullable=True, server_default='0'),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transactions_user_id', 'transactions', ['user_id'], unique=False)
    op.create_index('idx_transactions_symbol', 'transactions', ['symbol'], unique=False)

    # Performance Snapshots
    op.create_table(
        'performance_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('portfolio_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('daily_return', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('cumulative_return', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_user_performance_date')
    )
    op.create_index('idx_performance_user_date', 'performance_snapshots', ['user_id', 'date'], unique=False)

    # Contact Requests
    op.create_table(
        'contact_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('client_type', sa.String(length=50), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Activity Log
    op.create_table(
        'activity_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_activity_user_id', 'activity_log', ['user_id'], unique=False)

def downgrade() -> None:
    op.drop_index('idx_activity_user_id', table_name='activity_log')
    op.drop_table('activity_log')
    op.drop_table('contact_requests')
    op.drop_index('idx_performance_user_date', table_name='performance_snapshots')
    op.drop_table('performance_snapshots')
    op.drop_index('idx_transactions_symbol', table_name='transactions')
    op.drop_index('idx_transactions_user_id', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index('idx_positions_user_id', table_name='positions')
    op.drop_table('positions')
    op.drop_table('users')
