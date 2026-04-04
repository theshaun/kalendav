"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_username', 'users', ['username'])

    op.create_table(
        'calendars',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=True, server_default='#3B82F6'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calendars_user_id', 'calendars', ['user_id'])

    op.create_table(
        'calendar_shares',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('calendar_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('permission', sa.Enum('read', 'write', 'admin', name='sharepermission'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calendar_shares_calendar_id', 'calendar_shares', ['calendar_id'])
    op.create_index('ix_calendar_shares_user_id', 'calendar_shares', ['user_id'])

    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('calendar_id', sa.Integer(), nullable=False),
        sa.Column('uid', sa.String(255), nullable=False),
        sa.Column('summary', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('dtstart', sa.DateTime(), nullable=False),
        sa.Column('dtend', sa.DateTime(), nullable=True),
        sa.Column('is_all_day', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('location', sa.String(500), nullable=True),
        sa.Column('rrule', sa.Text(), nullable=True),
        sa.Column('raw_ics', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_events_calendar_id', 'events', ['calendar_id'])
    op.create_index('ix_events_uid', 'events', ['uid'])
    op.create_index('ix_events_calendar_uid', 'events', ['calendar_id', 'uid'], unique=True)

    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('permissions', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'])


def downgrade() -> None:
    op.drop_index('ix_api_keys_key_hash', 'api_keys')
    op.drop_index('ix_api_keys_user_id', 'api_keys')
    op.drop_table('api_keys')
    
    op.drop_index('ix_events_calendar_uid', 'events')
    op.drop_index('ix_events_uid', 'events')
    op.drop_index('ix_events_calendar_id', 'events')
    op.drop_table('events')
    
    op.drop_index('ix_calendar_shares_user_id', 'calendar_shares')
    op.drop_index('ix_calendar_shares_calendar_id', 'calendar_shares')
    op.drop_table('calendar_shares')
    
    op.drop_index('ix_calendars_user_id', 'calendars')
    op.drop_table('calendars')
    
    op.drop_index('ix_users_username', 'users')
    op.drop_table('users')
