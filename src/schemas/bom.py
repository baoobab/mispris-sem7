from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import model_validator
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------- запросы
class BomComponentAdd(SQLModel):
    """Добавление компонента в спецификацию изделия."""

    component_item_id: int
    quantity: Decimal = Field(gt=0, description="Расход компонента (в ЕИ unit_quantity_id)")
    for_quantity: Decimal = Field(default=Decimal("1"), gt=0, description="На какое количество изделия дан расход")
    unit_quantity_id: Optional[int] = Field(default=None, description="ЕИ компонента; по умолчанию базовая ЕИ")
    is_base: bool = Field(default=True, description="Флаг базы: строка наследуется модификациями")
    order_number: int = Field(default=0, ge=0)
    reason: Optional[str] = Field(default=None, max_length=500)


class BomComponentUpdate(SQLModel):
    """Изменение нормы расхода/реквизитов компонента (создаёт новую версию строки)."""

    quantity: Optional[Decimal] = Field(default=None, gt=0)
    for_quantity: Optional[Decimal] = Field(default=None, gt=0)
    unit_quantity_id: Optional[int] = None
    is_base: Optional[bool] = None
    order_number: Optional[int] = Field(default=None, ge=0)
    reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BomComponentUpdate":
        fields = ("quantity", "for_quantity", "unit_quantity_id", "is_base", "order_number")
        if all(getattr(self, f) is None for f in fields):
            raise ValueError("Нужно указать хотя бы одно изменяемое поле")
        return self


class BomComponentReplace(SQLModel):
    """Замена компонента другим."""

    new_component_item_id: int
    quantity: Decimal = Field(gt=0)
    for_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_quantity_id: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class ModificationCreate(SQLModel):
    """CREATE_MODIFICATION: новая модификация на основе базового изделия."""

    name: str = Field(min_length=1, max_length=500)
    number: Optional[str] = Field(default=None, max_length=50, description="По умолчанию <обозначение базы>-01, -02, ... (исполнения по ЕСКД)")
    article: Optional[str] = Field(default=None, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------- ответы
class BomRowRead(SQLModel):
    """Строка действующей спецификации (один уровень)."""

    bom_id: int
    configuration_function_id: Optional[int] = None
    owner_item_id: int
    inherited: bool
    inherit_level: int
    component_item_id: int
    component_number: str
    component_name: str
    component_type: Optional[str]
    class_id: Optional[int]
    class_name: Optional[str]
    quantity: Decimal
    for_quantity: Decimal
    unit_quantity_id: Optional[int]
    unit_symbol: Optional[str]
    base_unit_symbol: Optional[str]
    is_base: bool
    is_excluded: bool
    order_number: int


class BomSpecRead(SQLModel):
    item_id: int
    item_name: str
    base_item_id: Optional[int]
    at: datetime
    rows: List[BomRowRead]


class BomTreeNode(SQLModel):
    """Узел полного дерева состава (FIND_BOM)."""

    lvl: int
    path: List[int]
    parent_item_id: int
    component_item_id: int
    component_number: str
    component_name: str
    component_type: Optional[str]
    class_id: Optional[int]
    class_name: Optional[str]
    bom_id: int
    owner_item_id: int
    inherited: bool
    quantity: Decimal
    for_quantity: Decimal
    unit_symbol: Optional[str]
    qty_base: Decimal
    base_unit_symbol: Optional[str]
    norm: Decimal = Field(description="Расход в базовой ЕИ компонента на 1 ед. корневого изделия")
    is_cycle: bool


class BomTreeRead(SQLModel):
    item_id: int
    item_name: str
    at: datetime
    nodes: List[BomTreeNode]


class NormRow(SQLModel):
    component_item_id: int
    component_number: str
    component_name: str
    component_type: Optional[str]
    class_id: Optional[int]
    class_name: Optional[str]
    base_unit_symbol: Optional[str]
    total_quantity: Decimal


class NormsRead(SQLModel):
    """Сводные нормы расхода (CALC_BOM)."""

    item_id: int
    item_name: str
    quantity: Decimal
    class_id: Optional[int]
    at: datetime
    rows: List[NormRow]


class BomVersion(SQLModel):
    bom_id: int
    configuration_function_id: Optional[int] = None
    component_item_id: int
    component_name: str
    quantity: Decimal
    for_quantity: Decimal
    is_excluded: bool
    valid_from: datetime
    valid_to: Optional[datetime]


class ChangeRead(SQLModel):
    """Запись истории изменений: что, когда, почему; версии «было» и «стало»."""

    id: int
    item_id: int
    change_type: str
    change_type_name: str
    change_date: datetime
    reason: Optional[str]
    old: Optional[BomVersion]
    new: Optional[BomVersion]
