"""Справочники и граф состояний изделия для маршрутной технологии."""

from decimal import Decimal
from typing import ClassVar

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class TechnologyClass(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_class"
    __table_args__ = (
        UniqueConstraint("kind", "code"),
        CheckConstraint("kind IN ('operation', 'profession', 'work_center')", name="ck_technology_class_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(max_length=20)
    code: str = Field(max_length=50)
    name: str = Field(max_length=255)
    parent_id: int | None = Field(default=None, foreign_key="technology_class.id")


class WorkCenter(SQLModel, table=True):
    __tablename__: ClassVar[str] = "work_center"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, unique=True)
    name: str = Field(max_length=255)
    class_id: int = Field(foreign_key="technology_class.id")
    sxd_id: int = Field(foreign_key="sxd.id")


class TechnologyAssetModel(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_asset_model"
    __table_args__ = (
        CheckConstraint("kind IN ('equipment', 'tool', 'fixture')", name="ck_technology_asset_model_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, unique=True)
    name: str = Field(max_length=255)
    kind: str = Field(max_length=20)


class TechnologyAsset(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_asset"

    id: int | None = Field(default=None, primary_key=True)
    inventory_number: str = Field(max_length=50, unique=True)
    model_id: int = Field(foreign_key="technology_asset_model.id")
    work_center_id: int = Field(foreign_key="work_center.id")


class TechnologyTemplate(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_template"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=50, unique=True)
    name: str = Field(max_length=255)
    definition: dict = Field(sa_column=Column(JSONB, nullable=False))


class TechnologyApplication(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_application"

    item_id: int = Field(primary_key=True, foreign_key="item.id")
    template_id: int = Field(foreign_key="technology_template.id")
    parameters: dict = Field(sa_column=Column(JSONB, nullable=False))
    resources: dict = Field(sa_column=Column(JSONB, nullable=False))


class TechnologyOperation(SQLModel, table=True):
    """Покупное или произведённое состояние изделия."""

    __tablename__: ClassVar[str] = "technology_operation"
    __table_args__ = (
        UniqueConstraint("item_id", "number"),
        Index("ux_technology_operation_output", "item_id", unique=True, postgresql_where=text("is_output")),
        CheckConstraint("number > 0", name="ck_technology_operation_number"),
        CheckConstraint(
            "(kind = 'purchase' AND class_id IS NULL AND work_center_id IS NULL "
            "AND profession_id IS NULL AND qualification_id IS NULL AND setup_minutes = 0 AND piece_minutes = 0) "
            "OR (kind = 'production' AND class_id IS NOT NULL AND work_center_id IS NOT NULL "
            "AND profession_id IS NOT NULL AND qualification_id IS NOT NULL)",
            name="ck_technology_operation_kind",
        ),
        CheckConstraint("setup_minutes >= 0 AND piece_minutes >= 0", name="ck_technology_operation_time"),
        CheckConstraint(
            "(template_id IS NULL AND template_step_number IS NULL) "
            "OR (template_id IS NOT NULL AND template_step_number IS NOT NULL AND template_step_number > 0)",
            name="ck_technology_operation_template_step",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="item.id")
    output_unit_id: int = Field(foreign_key="unit_quantity.id")
    number: int
    name: str = Field(max_length=255)
    kind: str = Field(max_length=20)
    is_output: bool = False
    class_id: int | None = Field(default=None, foreign_key="technology_class.id")
    work_center_id: int | None = Field(default=None, foreign_key="work_center.id")
    profession_id: int | None = Field(default=None, foreign_key="technology_class.id")
    qualification_id: int | None = Field(default=None, foreign_key="enum_value.id")
    template_id: int | None = Field(default=None, foreign_key="technology_template.id")
    template_step_number: int | None = None
    setup_minutes: Decimal = Field(default=Decimal(0), max_digits=24, decimal_places=9)
    piece_minutes: Decimal = Field(default=Decimal(0), max_digits=24, decimal_places=9)


class TechnologyInput(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_input"
    __table_args__ = (
        CheckConstraint("out_operation_id <> in_operation_id", name="ck_technology_input_not_self"),
        CheckConstraint("quantity > 0 AND for_quantity > 0", name="ck_technology_input_quantity"),
    )

    out_operation_id: int = Field(
        sa_column=Column(Integer, ForeignKey("technology_operation.id", ondelete="CASCADE"), primary_key=True)
    )
    in_operation_id: int = Field(primary_key=True, foreign_key="technology_operation.id", index=True)
    quantity: Decimal = Field(max_digits=24, decimal_places=9)
    for_quantity: Decimal = Field(default=Decimal(1), max_digits=24, decimal_places=9)
    unit_quantity_id: int = Field(foreign_key="unit_quantity.id")


class TechnologyToolRequirement(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_tool_requirement"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_technology_tool_requirement_quantity"),)

    operation_id: int = Field(
        sa_column=Column(Integer, ForeignKey("technology_operation.id", ondelete="CASCADE"), primary_key=True)
    )
    model_id: int = Field(primary_key=True, foreign_key="technology_asset_model.id")
    quantity: int


class TechnologyLaborRate(SQLModel, table=True):
    __tablename__: ClassVar[str] = "technology_labor_rate"
    __table_args__ = (CheckConstraint("hourly_rate >= 0", name="ck_technology_labor_rate"),)

    profession_id: int = Field(primary_key=True, foreign_key="technology_class.id")
    qualification_id: int = Field(primary_key=True, foreign_key="enum_value.id")
    hourly_rate: Decimal = Field(max_digits=18, decimal_places=2)
