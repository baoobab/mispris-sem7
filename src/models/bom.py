from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field, SQLModel


class ItemBom(SQLModel, table=True):
    """Позиция материальной спецификации (BOM, SPEC_PROD).

    Строки версионируются: правка не перезаписывает строку, а закрывает её
    (valid_to) и создаёт новую версию. Действующая строка — valid_to IS NULL.

    is_base     — «флаг базы»: строка входит в базовую спецификацию и
                  наследуется модификациями изделия.
    is_excluded — строка-исключение модификации: компонент базового изделия
                  в модификацию не входит.
    """

    __tablename__: ClassVar[str] = "item_bom"
    __table_args__ = (
        CheckConstraint("parent_item_id <> component_item_id", name="ck_item_bom_not_self"),
        CheckConstraint("quantity > 0 OR is_excluded", name="ck_item_bom_quantity_positive"),
        CheckConstraint("for_quantity > 0", name="ck_item_bom_for_quantity_positive"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_item_bom_valid_period"),
        Index(
            "ux_item_bom_active_component",
            "parent_item_id",
            "component_item_id",
            text("coalesce(configuration_function_id,0)"),
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index("ix_item_bom_parent", "parent_item_id"),
        Index("ix_item_bom_component", "component_item_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    parent_item_id: int = Field(foreign_key="item.id")
    component_item_id: int = Field(foreign_key="item.id")
    configuration_function_id: Optional[int] = Field(default=None, foreign_key="bom_function.function_id")
    quantity: Decimal = Field(decimal_places=6, max_digits=18)
    for_quantity: Decimal = Field(default=Decimal("1"), decimal_places=6, max_digits=18)
    unit_quantity_id: Optional[int] = Field(default=None, foreign_key="unit_quantity.id", ondelete="RESTRICT")
    is_base: bool = Field(default=True)
    is_excluded: bool = Field(default=False)
    order_number: int = Field(default=0)
    valid_from: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    valid_to: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ItemChange(SQLModel, table=True):
    """Факт изменения спецификации изделия (REGISTER_CHANGE).

    old_bom_id / new_bom_id — версии позиции до и после изменения,
    по ним восстанавливается полный «было → стало».
    """

    __tablename__: ClassVar[str] = "item_change"

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="item.id")
    old_bom_id: Optional[int] = Field(default=None, foreign_key="item_bom.id")
    new_bom_id: Optional[int] = Field(default=None, foreign_key="item_bom.id")
    change_type_id: int = Field(foreign_key="enum_value.id")
    change_date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    reason: Optional[str] = Field(default=None, max_length=500)
