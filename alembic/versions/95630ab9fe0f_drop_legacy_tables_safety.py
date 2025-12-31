"""drop_legacy_tables_safety

Revision ID: 95630ab9fe0f
Revises: 09cb35b9b49c
Create Date: 2025-12-31 11:17:24.409301

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '95630ab9fe0f'
down_revision = '09cb35b9b49c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Safety migration to ensure all legacy tables are dropped.
    These tables were replaced by the new criteria-focused schema:
    - serology_results, culture_results -> laboratory_results
    - topic_results, component_results -> criteria_evaluations
    - donor_extractions, donor_extraction_vectors -> removed (data in criteria_evaluations)
    - donor_anchor_decisions -> removed (replaced by donor_eligibility)
    """
    # Drop legacy tables if they still exist (safety check)
    # Using IF EXISTS to avoid errors if tables were already dropped
    op.execute("DROP TABLE IF EXISTS serology_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS culture_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS topic_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS component_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_extractions CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_extraction_vectors CASCADE;")
    op.execute("DROP TABLE IF EXISTS donor_anchor_decisions CASCADE;")


def downgrade() -> None:
    """
    Note: Legacy tables are not recreated in downgrade.
    They have been permanently replaced by the new schema.
    If you need to restore them, you would need to recreate them from previous migrations.
    """
    pass


