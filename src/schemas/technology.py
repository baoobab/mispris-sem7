from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Id = Annotated[int, Field(gt=0, le=2_147_483_647)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ClassKind = Literal["operation", "profession", "work_center"]
AssetKind = Literal["equipment", "tool", "fixture"]
Amount = Annotated[Decimal, Field(max_digits=24, decimal_places=9, allow_inf_nan=False)]
PositiveAmount = Annotated[Amount, Field(gt=0)]
NonnegativeAmount = Annotated[Amount, Field(ge=0)]
MoneyRate = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)]


class TechnologySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class NamedCreate(TechnologySchema):
    code: Code
    name: Name


class ClassCreate(NamedCreate):
    kind: ClassKind
    parent_id: Id | None = None


class ClassRead(ClassCreate):
    id: int


class WorkCenterCreate(NamedCreate):
    class_id: Id
    sxd_id: Id


class WorkCenterRead(WorkCenterCreate):
    id: int


class AssetModelCreate(NamedCreate):
    kind: AssetKind


class AssetModelRead(AssetModelCreate):
    id: int


class AssetCreate(TechnologySchema):
    inventory_number: Code
    model_id: Id
    work_center_id: Id


class AssetRead(AssetCreate):
    id: int


class ToolQuantity(TechnologySchema):
    quantity: Id = 1


class ToolRead(ToolQuantity):
    operation_id: int
    model_id: int


class OperationDetails(TechnologySchema):
    number: Id
    name: Name
    kind: Literal["purchase", "production"]
    is_output: bool = False
    class_id: Id | None = None
    work_center_id: Id | None = None
    profession_id: Id | None = None
    qualification_id: Id | None = None

    @model_validator(mode="after")
    def validate_kind(self):
        refs = (self.class_id, self.work_center_id, self.profession_id, self.qualification_id)
        if self.kind == "purchase" and any(ref is not None for ref in refs):
            raise ValueError("Для закупки не задаются класс операции, ГРЦ, профессия и квалификация")
        if self.kind == "production" and any(ref is None for ref in refs):
            raise ValueError("Для производства нужны класс операции, ГРЦ, профессия и квалификация")
        return self


class OperationCreate(OperationDetails):
    setup_minutes: NonnegativeAmount = Decimal(0)
    piece_minutes: NonnegativeAmount = Decimal(0)

    @model_validator(mode="after")
    def validate_times(self):
        if self.kind == "purchase" and (self.setup_minutes or self.piece_minutes):
            raise ValueError("Для закупки не задаётся трудоёмкость")
        return self


class OperationRead(OperationCreate):
    id: int
    item_id: int
    output_unit_id: int
    template_id: int | None = None
    template_step_number: int | None = None


class RouteOperation(OperationRead):
    depth: int


class InputNorm(TechnologySchema):
    quantity: PositiveAmount
    for_quantity: PositiveAmount = Decimal(1)
    unit_quantity_id: Id | None = None


class InputRead(InputNorm):
    out_operation_id: int
    in_operation_id: int
    unit_quantity_id: int


class OperationWithResources(OperationRead):
    inputs: list[InputRead]
    tools: list[ToolRead]


class RouteRead(TechnologySchema):
    item_id: int
    output_operation_id: int
    operations: list[RouteOperation]
    inputs: list[InputRead]
    tools: list[ToolRead]


class MaterialQuantity(TechnologySchema):
    item_id: int
    unit_quantity_id: int
    quantity: Decimal


class MaterialNorm(MaterialQuantity):
    item_name: str = Field(description="Название ресурса")
    unit_symbol: str = Field(description="Обозначение базовой единицы измерения ресурса")


class OperationMaterialNorm(MaterialNorm):
    in_operation_id: int


class LaborNorm(TechnologySchema):
    profession_id: int
    qualification_id: int
    setup_minutes: Decimal
    piece_minutes: Decimal
    total_minutes: Decimal


class LaborRate(TechnologySchema):
    hourly_rate: MoneyRate


class LaborRateRead(LaborRate):
    profession_id: int
    qualification_id: int


class MaterialCost(MaterialQuantity):
    price: Decimal
    cost: Decimal


class LaborCost(LaborNorm):
    hourly_rate: Decimal
    cost: Decimal


class CostRead(TechnologySchema):
    item_id: int
    quantity: Decimal
    pricelist_set_id: int
    materials: list[MaterialCost]
    labor: list[LaborCost]
    material_cost: Decimal
    labor_cost: Decimal
    total_cost: Decimal


class Formula(TechnologySchema):
    """Значение = constant + сумма коэффициентов, умноженных на параметры."""

    constant: Amount = Decimal(0)
    factors: dict[Code, Amount] = Field(default_factory=dict)

    def evaluate(self, values: dict[str, Decimal]) -> Decimal:
        return self.constant + sum((coefficient * values[name] for name, coefficient in self.factors.items()), Decimal(0))


class TemplateInput(TechnologySchema):
    input_number: Id | None = None
    input_key: Code | None = None
    quantity: Formula
    for_quantity: PositiveAmount = Decimal(1)

    @model_validator(mode="after")
    def validate_reference(self):
        if (self.input_number is None) == (self.input_key is None):
            raise ValueError("Укажите номер шага шаблона или ключ внешнего ресурса")
        return self


class TemplateStep(OperationDetails):
    setup_minutes: Formula = Field(default_factory=Formula)
    piece_minutes: Formula = Field(default_factory=Formula)
    inputs: list[TemplateInput] = Field(default_factory=list)
    tools: dict[Id, Id] = Field(default_factory=dict)


class TemplateDefinition(TechnologySchema):
    parameters: list[Code] = Field(default_factory=list)
    steps: list[TemplateStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self):
        parameters = set(self.parameters)
        if len(parameters) != len(self.parameters):
            raise ValueError("Параметры шаблона должны быть уникальными")
        steps = {s.number: s for s in self.steps}
        outputs = [s for s in self.steps if s.is_output]
        if len(steps) != len(self.steps) or len(outputs) != 1:
            raise ValueError("Номера шагов должны быть уникальными, выходная операция должна быть одна")
        for step in self.steps:
            times = (step.setup_minutes, step.piece_minutes)
            if step.kind == "purchase" and (
                step.inputs or step.tools or any(t.constant or t.factors for t in times)
            ):
                raise ValueError("Шаг закупки не может иметь входов, оснастки или трудоёмкости")
            keys = {(e.input_number, e.input_key) for e in step.inputs}
            if len(keys) != len(step.inputs):
                raise ValueError("Входы шага не должны повторяться")
            for edge in step.inputs:
                if edge.input_number is not None and (edge.input_number not in steps or edge.input_number >= step.number):
                    raise ValueError("Внутренний вход должен ссылаться на предыдущий шаг")
            for formula in (*times, *(e.quantity for e in step.inputs)):
                if formula.factors.keys() - parameters:
                    raise ValueError("Формула использует необъявленный параметр")
        reachable = set()
        pending = [outputs[0].number]
        while pending:
            number = pending.pop()
            if number not in reachable:
                reachable.add(number)
                pending.extend(e.input_number for e in steps[number].inputs if e.input_number is not None)
        if reachable != steps.keys():
            raise ValueError("Все шаги шаблона должны входить в граф выходной операции")
        return self


class TemplateCreate(NamedCreate):
    definition: TemplateDefinition


class TemplateRead(TemplateCreate):
    id: int


class ResourceBinding(TechnologySchema):
    operation_id: Id
    unit_quantity_id: Id | None = None


class TemplateApply(TechnologySchema):
    parameters: dict[Code, Amount] = Field(default_factory=dict)
    resources: dict[Code, ResourceBinding] = Field(default_factory=dict)


class ApplicationRead(TechnologySchema):
    item_id: int
    template_id: int
    parameters: dict[str, Decimal]
    resources: dict[str, ResourceBinding]
