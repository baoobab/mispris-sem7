from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext

from pydantic import ValidationError

from src.core.errors import BusinessRuleError, ConflictError, NotFoundError
from src.models import (
    EnumType, EnumValue, Item, PricelistSet, Sxd, TechnologyApplication, TechnologyAsset, TechnologyAssetModel,
    TechnologyClass, TechnologyInput, TechnologyOperation, TechnologyTemplate, TechnologyToolRequirement,
    UnitQuantity, WorkCenter,
)
from src.repository.bom_repository import ItemBomRepository, ItemCatalogRepository
from src.repository.item_repository import UnitQuantityRepository
from src.repository.technology_repository import TechnologyRepository
from src.schemas.technology import (
    AssetCreate, ClassCreate, Formula, InputNorm, OperationCreate, OperationRead, RouteOperation, TemplateApply,
    TemplateCreate, TemplateDefinition, WorkCenterCreate,
)
from src.services.bom_calculator import BomCalculator


class TechnologyService:
    def __init__(self, repo: TechnologyRepository):
        self.repo = repo

    def require(self, model, key, label):
        row = self.repo.get(model, key)
        if row is None:
            raise NotFoundError(f"{label} ({key}) не найден")
        return row

    def _class(self, class_id: int, kind: str):
        row = self.require(TechnologyClass, class_id, "Класс")
        if row.kind != kind:
            raise BusinessRuleError(f"Класс {class_id} должен относиться к классификатору {kind}")
        return row

    def _enum(self, value_id: int, type_code: str):
        value = self.require(EnumValue, value_id, "Значение перечисления")
        enum_type = self.repo.get(EnumType, value.enum_type_id)
        if enum_type.code != type_code:
            raise BusinessRuleError(f"Значение {value_id} должно относиться к перечислению {type_code}")
        return value

    def save_class(self, data: ClassCreate, class_id: int | None = None):
        if class_id is not None:
            row = self._class(class_id, data.kind)
        else:
            row = TechnologyClass()
        if data.parent_id is not None:
            # Смена родителя проверяется под тем же замком, что и правки графа.
            self.repo.lock_graph()
            parent = self._class(data.parent_id, data.kind)
            seen = set()
            while parent is not None:
                if parent.id == class_id or parent.id in seen:
                    raise BusinessRuleError("Родитель создаёт цикл в классификаторе")
                seen.add(parent.id)
                parent = self.repo.get(TechnologyClass, parent.parent_id) if parent.parent_id is not None else None
        return self._save(row, data.model_dump())

    def save_work_center(self, data: WorkCenterCreate, center_id: int | None = None):
        self._class(data.class_id, "work_center")
        sxd = self.require(Sxd, data.sxd_id, "СХД")
        if self._enum(sxd.entity_type_id, "sxd_type").code != "dept":
            raise BusinessRuleError("ГРЦ должен быть привязан к подразделению")
        row = self.require(WorkCenter, center_id, "ГРЦ") if center_id is not None else WorkCenter()
        return self._save(row, data.model_dump())

    def save_asset(self, data: AssetCreate, asset_id: int | None = None):
        self.require(TechnologyAssetModel, data.model_id, "Модель средства труда")
        self.require(WorkCenter, data.work_center_id, "ГРЦ")
        row = self.require(TechnologyAsset, asset_id, "Инвентарная единица") if asset_id is not None else TechnologyAsset()
        return self._save(row, data.model_dump())

    def _save(self, row, values):
        for key, value in values.items():
            setattr(row, key, value)
        return self.repo.save(row)

    def _operation(self, item_id: int, operation_id: int):
        row = self.require(TechnologyOperation, operation_id, "Позиция маршрута")
        if row.item_id != item_id:
            raise NotFoundError(f"Операция {operation_id} не входит в маршрут изделия {item_id}")
        return row

    def _base_unit(self, item_id: int):
        unit = UnitQuantityRepository(self.repo.session).get_base_unit(item_id)
        if unit is None:
            raise BusinessRuleError(f"У изделия {item_id} должна быть базовая единица количества")
        return unit

    def _check_operation_refs(self, data):
        if data.kind == "production":
            self._class(data.class_id, "operation")
            self.require(WorkCenter, data.work_center_id, "ГРЦ")
            self._class(data.profession_id, "profession")
            self._enum(data.qualification_id, "qualification")

    def list_operations(self, item_id: int):
        self.require(Item, item_id, "Изделие")
        return self.repo.operations(item_id)

    def get_operation(self, item_id: int, operation_id: int):
        self.repo.lock_graph(shared=True)
        row = self._operation(item_id, operation_id)
        return dict(
            **OperationRead.model_validate(row).model_dump(),
            inputs=self.repo.inputs([operation_id]), tools=self.repo.tools([operation_id]),
        )

    def save_operation(self, item_id: int, data: OperationCreate, operation_id: int | None = None):
        self.repo.lock_graph()
        return self._save_operation(item_id, data, operation_id)

    def _save_operation(
        self, item_id: int, data: OperationCreate, operation_id: int | None = None, *, template_id: int | None = None,
    ):
        self.require(Item, item_id, "Изделие")
        self._check_operation_refs(data)
        if operation_id is None:
            row = TechnologyOperation(
                item_id=item_id, output_unit_id=self._base_unit(item_id).id,
                template_id=template_id, template_step_number=data.number if template_id is not None else None,
            )
        else:
            row = self._operation(item_id, operation_id)
            for edge, linked in self.repo.linked_operations(operation_id):
                incoming = edge.out_operation_id == operation_id
                if incoming and data.kind == "purchase":
                    raise BusinessRuleError("У закупочной позиции не может быть входных ресурсов")
                if linked.item_id == item_id and (
                    (incoming and linked.number >= data.number) or (not incoming and linked.number <= data.number)
                ):
                    raise BusinessRuleError("Вход того же изделия должен быть предыдущей операцией")
            if data.kind == "purchase" and self.repo.tools([operation_id]):
                raise BusinessRuleError("У закупочной позиции не может быть требований к средствам труда")
        if data.is_output:
            previous = self.repo.output(item_id)
            if previous is not None and previous.id != operation_id:
                self._save(previous, {"is_output": False})
        return self._save(row, data.model_dump())

    def delete_operation(self, item_id: int, operation_id: int):
        self.repo.lock_graph()
        self.repo.delete(self._operation(item_id, operation_id))

    def put_input(self, item_id: int, operation_id: int, input_id: int, data: InputNorm):
        self.repo.lock_graph()
        output = self._operation(item_id, operation_id)
        return self._put_input(output, input_id, data)

    def _put_input(self, output: TechnologyOperation, input_id: int, data: InputNorm):
        if output.kind == "purchase":
            raise BusinessRuleError("Закупочная позиция не потребляет входные ресурсы")
        incoming = self.require(TechnologyOperation, input_id, "Входная позиция маршрута")
        if output.id == incoming.id or self.repo.creates_cycle(output.id, incoming.id):
            raise BusinessRuleError("Входной ресурс создаёт цикл в технологическом маршруте")
        if output.item_id == incoming.item_id and incoming.number >= output.number:
            raise BusinessRuleError("Вход того же изделия должен быть предыдущей операцией")
        unit_id = data.unit_quantity_id or incoming.output_unit_id
        unit = self.require(UnitQuantity, unit_id, "Единица количества")
        if unit.item_id != incoming.item_id or unit.coefficient <= 0:
            raise BusinessRuleError("Единица расхода должна принадлежать входному изделию и иметь положительный коэффициент")
        key = (output.id, input_id)
        edge = self.repo.get(TechnologyInput, key) or TechnologyInput(out_operation_id=output.id, in_operation_id=input_id)
        return self._save(edge, {"quantity": data.quantity, "for_quantity": data.for_quantity, "unit_quantity_id": unit_id})

    def delete_input(self, item_id: int, operation_id: int, input_id: int):
        self.repo.lock_graph()
        self._operation(item_id, operation_id)
        self.repo.delete(self.require(TechnologyInput, (operation_id, input_id), "Позиция входного ресурса"))

    def _put_tool(self, operation: TechnologyOperation, model_id: int, quantity: int):
        if operation.kind == "purchase":
            raise BusinessRuleError("Для закупки не задаются требования к средствам труда")
        self.require(TechnologyAssetModel, model_id, "Модель средства труда")
        key = (operation.id, model_id)
        row = self.repo.get(TechnologyToolRequirement, key) or TechnologyToolRequirement(
            operation_id=operation.id, model_id=model_id,
        )
        return self._save(row, {"quantity": quantity})

    def put_tool(self, item_id: int, operation_id: int, model_id: int, quantity: int):
        self.repo.lock_graph()
        return self._put_tool(self._operation(item_id, operation_id), model_id, quantity)

    def delete_tool(self, item_id: int, operation_id: int, model_id: int):
        self.repo.lock_graph()
        self._operation(item_id, operation_id)
        self.repo.delete(self.require(TechnologyToolRequirement, (operation_id, model_id), "Требование к средству труда"))

    def import_bom(self, item_id: int, operation_id: int, at: datetime | None):
        self.repo.lock_graph()
        operation = self._operation(item_id, operation_id)
        if operation.kind == "purchase":
            raise BusinessRuleError("Закупочная позиция не потребляет входные ресурсы")
        at = at or datetime.now(timezone.utc)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        calc = BomCalculator(ItemBomRepository(self.repo.session), ItemCatalogRepository(self.repo.session))
        imported = []
        for row in calc.effective(item_id, at):
            incoming = self.repo.output(row["component_item_id"])
            if incoming is None:
                raise ConflictError(f"У компонента BOM {row['component_item_id']} нет выходной операции маршрута")
            imported.append(self._put_input(operation, incoming.id, InputNorm(
                quantity=row["quantity"], for_quantity=row["for_quantity"], unit_quantity_id=row["unit_quantity_id"],
            )))
        return imported

    def _output(self, item_id: int):
        self.require(Item, item_id, "Изделие")
        output = self.repo.output(item_id)
        if output is None:
            raise NotFoundError(f"У изделия {item_id} не задана выходная операция маршрута")
        return output

    def find_route(self, item_id: int):
        self.repo.lock_graph(shared=True)
        output = self._output(item_id)
        rows = self.repo.route_operations(item_id)
        ids = [row.id for row, _ in rows]
        return dict(
            item_id=item_id, output_operation_id=output.id,
            operations=[
                RouteOperation(**OperationRead.model_validate(row).model_dump(), depth=depth) for row, depth in rows
            ],
            inputs=self.repo.inputs(ids), tools=self.repo.tools(ids),
        )

    def direct_materials(self, item_id: int, operation_id: int, quantity: Decimal):
        self.repo.lock_graph(shared=True)
        self._operation(item_id, operation_id)
        return self.repo.direct_materials(operation_id, quantity)

    def materials(self, item_id: int, quantity: Decimal):
        self.repo.lock_graph(shared=True)
        self._output(item_id)
        return self.repo.materials(item_id, quantity)

    def labor(self, item_id: int, quantity: Decimal):
        self.repo.lock_graph(shared=True)
        self._output(item_id)
        return self.repo.labor(item_id, quantity)

    def put_rate(self, profession_id: int, qualification_id: int, rate: Decimal):
        self._class(profession_id, "profession")
        self._enum(qualification_id, "qualification")
        return self.repo.put_rate(profession_id, qualification_id, rate)

    def cost(self, item_id: int, quantity: Decimal, price_set_id: int):
        self.repo.lock_graph(shared=True)
        self._output(item_id)
        self.require(PricelistSet, price_set_id, "Прейскурант")
        materials = self.repo.materials(item_id, quantity, price_set_id)
        labor = self.repo.labor(item_id, quantity, with_rates=True)
        missing_materials = sorted({m["item_id"] for m in materials if m["price"] is None})
        missing_labor = [(r["profession_id"], r["qualification_id"]) for r in labor if r["hourly_rate"] is None]
        if missing_materials or missing_labor:
            raise ConflictError(f"Не заданы цены материалов: {missing_materials}; ставки профессий и квалификаций: {missing_labor}")
        with localcontext() as ctx:
            ctx.prec = 60
            money = Decimal("0.01")
            material_lines = [
                dict(m, cost=(m["quantity"] * m["price"]).quantize(money, rounding=ROUND_HALF_UP)) for m in materials
            ]
            labor_lines = [
                dict(r, cost=(r["total_minutes"] * r["hourly_rate"] / 60).quantize(money, rounding=ROUND_HALF_UP))
                for r in labor
            ]
            material_cost = sum((m["cost"] for m in material_lines), Decimal("0.00"))
            labor_cost = sum((r["cost"] for r in labor_lines), Decimal("0.00"))
            return dict(
                item_id=item_id, quantity=quantity, pricelist_set_id=price_set_id, materials=material_lines,
                labor=labor_lines, material_cost=material_cost, labor_cost=labor_cost,
                total_cost=material_cost + labor_cost,
            )

    def create_template(self, data: TemplateCreate):
        for step in data.definition.steps:
            self._check_operation_refs(step)
            for model_id in step.tools:
                self.require(TechnologyAssetModel, model_id, "Модель средства труда")
        return self.repo.save(TechnologyTemplate(**data.model_dump(mode="json")))

    @staticmethod
    def _evaluate(formula: Formula, values: dict[str, Decimal]) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 60
            return formula.evaluate(values).quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)

    def apply_template(self, item_id: int, template_id: int, data: TemplateApply):
        self.repo.lock_graph()
        self.require(Item, item_id, "Изделие")
        template = self.require(TechnologyTemplate, template_id, "Типовой процесс")
        if self.repo.operations(item_id):
            raise ConflictError("Типовой процесс применяется к изделию без маршрута")
        definition = TemplateDefinition.model_validate(template.definition)
        external_keys = {e.input_key for s in definition.steps for e in s.inputs if e.input_key is not None}
        if data.parameters.keys() != set(definition.parameters) or data.resources.keys() != external_keys:
            raise BusinessRuleError("Укажите значения всех объявленных параметров и привязки всех внешних ресурсов")
        nodes = {}
        try:
            for step in sorted(definition.steps, key=lambda s: s.number):
                operation = OperationCreate(
                    **step.model_dump(exclude={"setup_minutes", "piece_minutes", "inputs", "tools"}),
                    setup_minutes=self._evaluate(step.setup_minutes, data.parameters),
                    piece_minutes=self._evaluate(step.piece_minutes, data.parameters),
                )
                node = nodes[step.number] = self._save_operation(item_id, operation, template_id=template_id)
                for edge in step.inputs:
                    if edge.input_number is not None:
                        resource_id, unit_id = nodes[edge.input_number].id, None
                    else:
                        binding = data.resources[edge.input_key]
                        resource_id, unit_id = binding.operation_id, binding.unit_quantity_id
                    if self.repo.get(TechnologyInput, (node.id, resource_id)) is not None:
                        raise BusinessRuleError("Разные входы шаблона привязаны к одному состоянию ресурса")
                    self._put_input(node, resource_id, InputNorm(
                        quantity=self._evaluate(edge.quantity, data.parameters),
                        for_quantity=edge.for_quantity, unit_quantity_id=unit_id,
                    ))
                for model_id, qty in step.tools.items():
                    self._put_tool(node, model_id, qty)
        except ValidationError as exc:
            raise BusinessRuleError("Результат формулы должен быть допустимой нормой расхода или трудоёмкости") from exc
        application = self.repo.get(TechnologyApplication, item_id) or TechnologyApplication(item_id=item_id)
        return self._save(application, {"template_id": template_id, **data.model_dump(mode="json")})
