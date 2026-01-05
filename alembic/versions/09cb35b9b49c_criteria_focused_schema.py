"""criteria_focused_schema

Revision ID: 09cb35b9b49c
Revises: add_user_feedback
Create Date: 2025-12-30 10:53:06.716860

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '09cb35b9b49c'
down_revision = 'add_user_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Create enums for new tables
    # TestType enum
    enum_check = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'testtype'
        )
    """))
    if not enum_check.scalar():
        op.execute("CREATE TYPE testtype AS ENUM ('serology', 'culture', 'other');")
    
    # EvaluationResult enum
    enum_check2 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'evaluationresult'
        )
    """))
    if not enum_check2.scalar():
        op.execute("CREATE TYPE evaluationresult AS ENUM ('acceptable', 'unacceptable', 'md_discretion');")
    
    # TissueType enum (for criteria_evaluations)
    enum_check3 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'criteriatissuetype'
        )
    """))
    if not enum_check3.scalar():
        op.execute("CREATE TYPE criteriatissuetype AS ENUM ('musculoskeletal', 'skin', 'both');")
    
    # EligibilityStatus enum
    enum_check4 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'eligibilitystatus'
        )
    """))
    if not enum_check4.scalar():
        op.execute("CREATE TYPE eligibilitystatus AS ENUM ('eligible', 'ineligible', 'requires_review');")
    
    # TissueType enum (for donor_eligibility)
    enum_check5 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'eligibilitytissuetype'
        )
    """))
    if not enum_check5.scalar():
        op.execute("CREATE TYPE eligibilitytissuetype AS ENUM ('musculoskeletal', 'skin');")
    
    # Create laboratory_results table
    op.execute("""
        CREATE TABLE IF NOT EXISTS laboratory_results (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            test_type testtype NOT NULL,
            test_name VARCHAR NOT NULL,
            test_method VARCHAR,
            result VARCHAR NOT NULL,
            specimen_type VARCHAR,
            specimen_date VARCHAR,
            comments TEXT,
            tissue_location VARCHAR,
            microorganism VARCHAR,
            source_page INTEGER,
            confidence FLOAT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS ix_laboratory_results_id ON laboratory_results(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_laboratory_results_document_id ON laboratory_results(document_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_laboratory_results_test_type ON laboratory_results(test_type);")
    
    # Create criteria_evaluations table
    op.execute("""
        CREATE TABLE IF NOT EXISTS criteria_evaluations (
            id SERIAL PRIMARY KEY,
            donor_id INTEGER NOT NULL REFERENCES donors(id),
            document_id INTEGER REFERENCES documents(id),
            criterion_name VARCHAR NOT NULL,
            tissue_type criteriatissuetype NOT NULL,
            extracted_data JSONB,
            evaluation_result evaluationresult NOT NULL,
            evaluation_reasoning TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS ix_criteria_evaluations_id ON criteria_evaluations(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_criteria_evaluations_donor_id ON criteria_evaluations(donor_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_criteria_evaluations_document_id ON criteria_evaluations(document_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_criteria_evaluations_criterion_name ON criteria_evaluations(criterion_name);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_criteria_evaluations_tissue_type ON criteria_evaluations(tissue_type);")
    
    # Create donor_eligibility table
    op.execute("""
        CREATE TABLE IF NOT EXISTS donor_eligibility (
            id SERIAL PRIMARY KEY,
            donor_id INTEGER NOT NULL REFERENCES donors(id),
            tissue_type eligibilitytissuetype NOT NULL,
            overall_status eligibilitystatus NOT NULL,
            blocking_criteria JSONB,
            md_discretion_criteria JSONB,
            evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            evaluated_by INTEGER REFERENCES users(id)
        );
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_eligibility_id ON donor_eligibility(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_eligibility_donor_id ON donor_eligibility(donor_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_eligibility_tissue_type ON donor_eligibility(tissue_type);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_donor_eligibility_donor_tissue ON donor_eligibility(donor_id, tissue_type);")
    
    # Drop old tables (no migration needed since no users)
    op.execute("DROP TABLE IF EXISTS serology_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS culture_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS topic_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS component_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_extractions CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_extraction_vectors CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_anchor_decisions CASCADE;")


def downgrade() -> None:
    # Drop new tables
    op.execute("DROP TABLE IF EXISTS donor_eligibility CASCADE;")
    op.execute("DROP TABLE IF EXISTS criteria_evaluations CASCADE;")
    op.execute("DROP TABLE IF EXISTS laboratory_results CASCADE;")
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS eligibilitytissuetype CASCADE;")
    op.execute("DROP TYPE IF EXISTS eligibilitystatus CASCADE;")
    op.execute("DROP TYPE IF EXISTS criteriatissuetype CASCADE;")
    op.execute("DROP TYPE IF EXISTS evaluationresult CASCADE;")
    op.execute("DROP TYPE IF EXISTS testtype CASCADE;")
    
    # Note: Old tables are not recreated in downgrade since they were dropped
    # If needed, they would need to be recreated from previous migrations
