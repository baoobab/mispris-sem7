from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PredicateInput(StrictInput):
    parameter_id: int
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"] = "eq"
    value_number: Decimal | None = Field(default=None, max_digits=18, decimal_places=6)
    value_text: str | None = Field(default=None, max_length=500)
    enum_value_id: int | None = None

    @model_validator(mode="after")
    def single_value(self):
        if sum(v is not None for v in (self.value_number, self.value_text, self.enum_value_id)) != 1:
            raise ValueError("Нужно ровно одно типизированное значение предиката")
        return self


class FunctionInput(StrictInput):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=255)
    # Пустая дизъюнкция = FALSE, пустая конъюнкция = TRUE (определения ТЗ).
    conjunctions: list[list[PredicateInput]] = Field(max_length=100)


class ConditionInput(StrictInput):
    function_id: int | None = None
    reason: str | None = Field(default=None, max_length=500)


class PositionInput(ConditionInput):
    component_item_id: int
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    for_quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=18, decimal_places=6)
    unit_quantity_id: int | None = None
    is_base: bool = True
    order_number: int = Field(default=0, ge=0)


class BomPreviewInput(StrictInput):
    values: dict[str, object] = Field(default_factory=dict)
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=18, decimal_places=6)
    at: datetime | None = None


class ConfiguredNode(BaseModel):
    lvl: int
    path: list[int]
    parent_item_id: int
    component_item_id: int
    component_number: str
    component_name: str
    bom_id: int
    function_id: int | None
    quantity: Decimal
    for_quantity: Decimal
    unit_quantity_id: int | None
    norm: Decimal
    total_quantity: Decimal
    base_unit_symbol: str | None
    is_leaf: bool


class ConfiguredNorm(BaseModel):
    component_item_id: int
    component_number: str
    component_name: str
    base_unit_symbol: str | None
    total_quantity: Decimal


class ConfiguredBomRead(BaseModel):
    item_id: int
    source_item_id: int
    at: datetime
    quantity: Decimal
    nodes: list[ConfiguredNode]
    norms: list[ConfiguredNorm]
