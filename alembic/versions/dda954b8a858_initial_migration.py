"""Initial migration

Revision ID: dda954b8a858
Revises: 
Create Date: 2025-10-25 21:54:22.116440

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dda954b8a858'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums that will be used by other tables (must be created before tables that use them)
    # Use DO blocks to check if types exist before creating them (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM ('admin', 'doc_uploader', 'medical_director');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE documenttype AS ENUM ('MEDICAL_HISTORY', 'SEROLOGY_REPORT', 'LAB_RESULTS', 'RECOVERY_CULTURES', 'CONSENT_FORM', 'DEATH_CERTIFICATE', 'OTHER');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE documentstatus AS ENUM ('UPLOADED', 'PROCESSING', 'ANALYZING', 'REVIEWING', 'COMPLETED', 'FAILED', 'REJECTED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create users table first (required for foreign keys in other tables)
    # Check if table exists before creating (idempotent)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR NOT NULL UNIQUE,
                    hashed_password VARCHAR NOT NULL,
                    full_name VARCHAR NOT NULL,
                    role userrole NOT NULL,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE
                );
                CREATE INDEX ix_users_id ON users(id);
                CREATE INDEX ix_users_email ON users(email);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Drop enums
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS documenttype")
    
    # Drop users table
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
