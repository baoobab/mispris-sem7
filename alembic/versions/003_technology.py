"""Задание №6: маршрутная технология, её справочники и расчёты.

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def identifier():
    return sa.Column("id", sa.Integer, primary_key=True)


def label(name, length, **kwargs):
    return sa.Column(name, sa.String(length), nullable=False, **kwargs)


def ref(name, target, *, nullable=False, ondelete=None, primary_key=False):
    return sa.Column(
        name, sa.Integer, sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable, primary_key=primary_key,
    )


def amount(name, *, default=None):
    return sa.Column(name, sa.Numeric(24, 9), nullable=False, server_default=default)


def upgrade():
    op.create_table(
        "technology_class", identifier(), label("kind", 20), label("code", 50), label("name", 255),
        ref("parent_id", "technology_class.id", nullable=True),
        sa.UniqueConstraint("kind", "code"),
        sa.CheckConstraint("kind IN ('operation', 'profession', 'work_center')", name="ck_technology_class_kind"),
    )
    op.create_table(
        "work_center", identifier(), label("code", 50, unique=True), label("name", 255),
        ref("class_id", "technology_class.id"), ref("sxd_id", "sxd.id"),
    )
    op.create_table(
        "technology_asset_model", identifier(), label("code", 50, unique=True), label("name", 255), label("kind", 20),
        sa.CheckConstraint("kind IN ('equipment', 'tool', 'fixture')", name="ck_technology_asset_model_kind"),
    )
    op.create_table(
        "technology_asset", identifier(), label("inventory_number", 50, unique=True),
        ref("model_id", "technology_asset_model.id"), ref("work_center_id", "work_center.id"),
    )
    op.create_table(
        "technology_template", identifier(), label("code", 50, unique=True), label("name", 255),
        sa.Column("definition", JSONB, nullable=False),
    )
    op.create_table(
        "technology_application",
        ref("item_id", "item.id", primary_key=True), ref("template_id", "technology_template.id"),
        sa.Column("parameters", JSONB, nullable=False), sa.Column("resources", JSONB, nullable=False),
    )
    op.create_table(
        "technology_operation", identifier(), ref("item_id", "item.id"), ref("output_unit_id", "unit_quantity.id"),
        sa.Column("number", sa.Integer, nullable=False), label("name", 255), label("kind", 20),
        sa.Column("is_output", sa.Boolean, nullable=False, server_default=sa.false()),
        ref("class_id", "technology_class.id", nullable=True), ref("work_center_id", "work_center.id", nullable=True),
        ref("profession_id", "technology_class.id", nullable=True), ref("qualification_id", "enum_value.id", nullable=True),
        ref("template_id", "technology_template.id", nullable=True),
        sa.Column("template_step_number", sa.Integer, nullable=True),
        amount("setup_minutes", default="0"), amount("piece_minutes", default="0"),
        sa.UniqueConstraint("item_id", "number"),
        sa.CheckConstraint("number > 0", name="ck_technology_operation_number"),
        sa.CheckConstraint(
            "(kind = 'purchase' AND class_id IS NULL AND work_center_id IS NULL "
            "AND profession_id IS NULL AND qualification_id IS NULL AND setup_minutes = 0 AND piece_minutes = 0) "
            "OR (kind = 'production' AND class_id IS NOT NULL AND work_center_id IS NOT NULL "
            "AND profession_id IS NOT NULL AND qualification_id IS NOT NULL)",
            name="ck_technology_operation_kind",
        ),
        sa.CheckConstraint("setup_minutes >= 0 AND piece_minutes >= 0", name="ck_technology_operation_time"),
        sa.CheckConstraint(
            "(template_id IS NULL AND template_step_number IS NULL) "
            "OR (template_id IS NOT NULL AND template_step_number IS NOT NULL AND template_step_number > 0)",
            name="ck_technology_operation_template_step",
        ),
    )
    op.create_index("ux_technology_operation_output", "technology_operation", ["item_id"], unique=True,
                    postgresql_where=sa.text("is_output"))
    op.create_table(
        "technology_input",
        ref("out_operation_id", "technology_operation.id", ondelete="CASCADE", primary_key=True),
        ref("in_operation_id", "technology_operation.id", primary_key=True),
        amount("quantity"), amount("for_quantity", default="1"), ref("unit_quantity_id", "unit_quantity.id"),
        sa.CheckConstraint("out_operation_id <> in_operation_id", name="ck_technology_input_not_self"),
        sa.CheckConstraint("quantity > 0 AND for_quantity > 0", name="ck_technology_input_quantity"),
    )
    op.create_index("ix_technology_input_in_operation_id", "technology_input", ["in_operation_id"])
    op.create_table(
        "technology_tool_requirement",
        ref("operation_id", "technology_operation.id", ondelete="CASCADE", primary_key=True),
        ref("model_id", "technology_asset_model.id", primary_key=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_technology_tool_requirement_quantity"),
    )
    op.create_table(
        "technology_labor_rate",
        ref("profession_id", "technology_class.id", primary_key=True),
        ref("qualification_id", "enum_value.id", primary_key=True),
        sa.Column("hourly_rate", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("hourly_rate >= 0", name="ck_technology_labor_rate"),
    )
    op.execute("""
        INSERT INTO enum_type (code, name) VALUES ('qualification', 'Квалификация')
        ON CONFLICT (code) DO NOTHING
    """)
    create_functions()


def create_functions():
    op.execute("""
        CREATE FUNCTION find_tm(p_id_el integer)
        RETURNS TABLE(operation_id integer, depth integer)
        LANGUAGE sql STABLE AS $$
            WITH RECURSIVE route(id, depth, path) AS (
                SELECT id, 0, ARRAY[id] FROM technology_operation WHERE item_id = p_id_el AND is_output
                UNION ALL
                SELECT e.in_operation_id, r.depth + 1, r.path || e.in_operation_id
                FROM route r JOIN technology_input e ON e.out_operation_id = r.id
                WHERE NOT (e.in_operation_id = ANY(r.path))
            )
            SELECT id, min(depth) FROM route GROUP BY id ORDER BY min(depth), id
        $$
    """)
    op.execute("""
        CREATE FUNCTION mr_q(p_id_to integer, p_q numeric)
        RETURNS TABLE(in_operation_id integer, item_id integer, unit_quantity_id integer, quantity numeric)
        LANGUAGE sql STABLE AS $$
            SELECT i.id, i.item_id, i.output_unit_id,
                   p_q * e.quantity * CASE WHEN u.id = i.output_unit_id THEN 1 ELSE u.coefficient END
                       / e.for_quantity
            FROM technology_input e JOIN technology_operation i ON i.id = e.in_operation_id
                 JOIN unit_quantity u ON u.id = e.unit_quantity_id
            WHERE e.out_operation_id = p_id_to
            ORDER BY i.id
        $$
    """)
    op.execute("""
        CREATE FUNCTION technology_demands(p_id_el integer, p_q numeric)
        RETURNS TABLE(operation_id integer, quantity numeric)
        LANGUAGE sql STABLE AS $$
            WITH RECURSIVE demand(id, qty, path) AS (
                SELECT id, p_q, ARRAY[id] FROM technology_operation WHERE item_id = p_id_el AND is_output
                UNION ALL
                SELECT input.in_operation_id, input.quantity, d.path || input.in_operation_id
                FROM demand d CROSS JOIN LATERAL mr_q(d.id, d.qty) input
                WHERE NOT (input.in_operation_id = ANY(d.path))
            )
            SELECT id, sum(qty) FROM demand GROUP BY id
        $$
    """)
    op.execute("""
        CREATE FUNCTION sum_mr(p_id_el integer, p_q numeric)
        RETURNS TABLE(item_id integer, unit_quantity_id integer, quantity numeric)
        LANGUAGE sql STABLE AS $$
            SELECT o.item_id, o.output_unit_id, sum(d.quantity)
            FROM technology_demands(p_id_el, p_q) d JOIN technology_operation o ON o.id = d.operation_id
            WHERE o.kind = 'purchase'
            GROUP BY o.item_id, o.output_unit_id ORDER BY o.item_id, o.output_unit_id
        $$
    """)
    op.execute("""
        CREATE FUNCTION tr_to(p_id_el integer, p_q numeric)
        RETURNS TABLE(profession_id integer, qualification_id integer,
                      setup_minutes numeric, piece_minutes numeric, total_minutes numeric)
        LANGUAGE sql STABLE AS $$
            SELECT o.profession_id, o.qualification_id, sum(o.setup_minutes),
                   sum(o.piece_minutes * d.quantity), sum(o.setup_minutes + o.piece_minutes * d.quantity)
            FROM technology_demands(p_id_el, p_q) d JOIN technology_operation o ON o.id = d.operation_id
            WHERE o.kind = 'production'
            GROUP BY o.profession_id, o.qualification_id ORDER BY o.profession_id, o.qualification_id
        $$
    """)
    # Перегрузки с сигнатурами из задания; API передаёт numeric, чтобы не терять точность.
    for name, result in (
        ("mr_q", "in_operation_id integer, item_id integer, unit_quantity_id integer, quantity numeric"),
        ("sum_mr", "item_id integer, unit_quantity_id integer, quantity numeric"),
        ("tr_to", "profession_id integer, qualification_id integer, "
                  "setup_minutes numeric, piece_minutes numeric, total_minutes numeric"),
    ):
        op.execute(f"""
            CREATE FUNCTION {name}(p_id integer, p_q double precision)
            RETURNS TABLE({result}) LANGUAGE sql STABLE AS $$
                SELECT * FROM {name}(p_id, CAST(p_q AS numeric))
            $$
        """)


def downgrade():
    for signature in (
        "tr_to(integer, double precision)", "sum_mr(integer, double precision)", "mr_q(integer, double precision)",
        "tr_to(integer, numeric)", "sum_mr(integer, numeric)", "technology_demands(integer, numeric)",
        "mr_q(integer, numeric)", "find_tm(integer)",
    ):
        op.execute(f"DROP FUNCTION {signature}")
    for table in (
        "technology_labor_rate", "technology_tool_requirement", "technology_input", "technology_operation",
        "technology_application", "technology_template", "technology_asset", "technology_asset_model",
        "work_center", "technology_class",
    ):
        op.drop_table(table)
    # Перечисление могло существовать до миграции и использоваться другими справочниками.
