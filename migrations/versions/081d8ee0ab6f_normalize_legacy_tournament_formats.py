"""normalize legacy tournament formats

Revision ID: 081d8ee0ab6f
Revises: 23ca203f6f8f
Create Date: 2026-09-03 22:39:59.952838

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '081d8ee0ab6f'
down_revision = '23ca203f6f8f'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE tournaments SET format = 'ROUND_ROBIN' WHERE format = 'Todos contra todos'")
    op.execute("UPDATE tournaments SET format = 'KNOCKOUT' WHERE format IN ('Eliminación directa', 'Eliminacion directa')")
    op.execute("UPDATE tournaments SET format = 'GROUPS_KNOCKOUT', group_count = CASE WHEN group_count < 2 THEN 2 ELSE group_count END WHERE format IN ('Grupos + Playoffs', 'Grupos + eliminación', 'Grupos + eliminacion')")


def downgrade():
    # Los rótulos anteriores no eran estables; conservar los identificadores canónicos.
    pass
