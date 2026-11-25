"""Задание №5: материальная спецификация изделий (Bill of Materials).

Процедуры задания и их реализация:
    FIND_BOM            -> BomService.find_bom      (BomCalculator.find_bom)
    CALC_BOM            -> BomService.calc_bom      (BomCalculator.calc_bom)
    CREATE_MODIFICATION -> BomService.create_modification
    REGISTER_CHANGE     -> BomService._register_change (вызывается каждой правкой состава)

Модель модификаций: модификация (item.base_item_id) не копирует спецификацию,
а наследует строки базовой спецификации (is_base) и хранит только отличия:
собственные строки (переопределение/добавление) и строки-исключения
(is_excluded). Изменения базового изделия автоматически видны в модификациях.

Версионирование: правка строки не перезаписывает её, а закрывает (valid_to)
и создаёт новую версию, поэтому состав можно получить на любую дату, а история
изменений хранит ссылки на версии «было» и «стало».
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence

from src.core.errors import BusinessRuleError, ConflictError, NotFoundError
from src.models.bom import ItemBom, ItemChange
from src.models.items import Item
from src.repository.bom_repository import (
    ItemBomRepository,
    ItemCatalogRepository,
    ItemChangeRepository,
    ModificationRepository,
)
from src.repository.classifier_repository import ItemClassifierRepository
from src.repository.enum_repository import EnumValueRepository
from src.repository.item_repository import ItemRepository, UnitQuantityRepository
from src.services.bom_calculator import BomCalculator
from src.schemas.bom import (
    BomComponentAdd,
    BomComponentReplace,
    BomComponentUpdate,
    BomRowRead,
    BomSpecRead,
    BomTreeNode,
    BomTreeRead,
    BomVersion,
    ChangeRead,
    ModificationCreate,
    NormRow,
    NormsRead,
)

ITEM_TYPE = "item_type"
CHANGE_TYPE = "bom_change_type"
MATERIAL = "material"


PRECISION = Decimal("0.000001")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rounded(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    """Расчёт идёт с полной точностью numeric, в ответе — 6 знаков после запятой."""
    return {k: (v.quantize(PRECISION) if k in fields and isinstance(v, Decimal) else v) for k, v in row.items()}


def next_modification_number(base_number: str, existing: set[str]) -> str:
    """Обозначение исполнения по ЕСКД: <обозначение базы>-01, -02, ..."""
    n = 1
    while f"{base_number}-{n:02d}" in existing:
        n += 1
    return f"{base_number}-{n:02d}"


class BomService:
    def __init__(
        self,
        items: ItemRepository,
        boms: ItemBomRepository,
        changes: ItemChangeRepository,
        modifications: ModificationRepository,
        enum_values: EnumValueRepository,
        units: UnitQuantityRepository,
        classifiers: ItemClassifierRepository,
        catalog: ItemCatalogRepository,
    ) -> None:
        self.items = items
        self.boms = boms
        self.changes = changes
        self.modifications = modifications
        self.enum_values = enum_values
        self.units = units
        self.classifiers = classifiers
        self.catalog = catalog
        self.calc = BomCalculator(boms, catalog)

    # ------------------------------------------------------------ helpers
    def _item(self, item_id: int) -> Item:
        item = self.items.get_by_id(item_id)
        if not item:
            raise NotFoundError(f"Изделие {item_id} не найдено")
        return item

    def _type_code(self, item: Item) -> Optional[str]:
        if item.item_type_id is None:
            return None
        ev = self.enum_values.get_by_id(item.item_type_id)
        return ev.code if ev else None

    def _ensure_can_have_spec(self, item: Item) -> None:
        if self._type_code(item) == MATERIAL:
            raise BusinessRuleError(
                f"Изделие «{item.name}» — материал: у материала не может быть спецификации"
            )

    def _change_type_id(self, code: str) -> int:
        ev = self.enum_values.get_by_codes(CHANGE_TYPE, code)
        if not ev or ev.id is None:
            raise BusinessRuleError(f"Не найден тип изменения '{code}' (перечисление {CHANGE_TYPE})")
        return ev.id

    def _register_change(
        self,
        item_id: int,
        change_code: str,
        old_bom_id: Optional[int],
        new_bom_id: Optional[int],
        reason: Optional[str],
        at: datetime,
    ) -> ItemChange:
        """REGISTER_CHANGE: регистрация факта изменения спецификации изделия."""
        return self.changes.create(
            {
                "item_id": item_id,
                "old_bom_id": old_bom_id,
                "new_bom_id": new_bom_id,
                "change_type_id": self._change_type_id(change_code),
                "change_date": at,
                "reason": reason,
            }
        )

    def _resolve_unit(self, unit_quantity_id: Optional[int], component: Item) -> Optional[int]:
        """ЕИ нормы расхода должна принадлежать компоненту; по умолчанию — его базовая ЕИ."""
        if unit_quantity_id is None:
            base = self.units.get_base_unit(component.id)  # type: ignore[arg-type]
            return base.id if base else None
        uq = self.units.get_by_id(unit_quantity_id)
        if not uq:
            raise NotFoundError(f"ЕИ количества {unit_quantity_id} не найдена")
        if uq.item_id != component.id:
            raise BusinessRuleError(
                f"ЕИ {unit_quantity_id} относится к другому изделию, а не к компоненту «{component.name}»"
            )
        return unit_quantity_id

    def _check_no_cycle(self, parent: Item, component: Item, at: datetime) -> None:
        if self.calc.has_cycle(parent.id, at):  # type: ignore[arg-type]
            raise BusinessRuleError(
                f"Добавление «{component.name}» в состав «{parent.name}» создаёт цикл в спецификации"
            )

    def _insert_row(self, parent: Item, component: Item, values: dict[str, Any], at: datetime) -> ItemBom:
        """Новая действующая строка; закрывает действующую строку-исключение того же компонента."""
        own = self.boms.get_own_active(parent.id, component.id)  # type: ignore[arg-type]
        if own is not None:
            if not own.is_excluded:
                raise ConflictError(f"Компонент «{component.name}» уже входит в состав «{parent.name}»")
            self.boms.close(own, at)
        return self.boms.create(
            {
                "parent_item_id": parent.id,
                "component_item_id": component.id,
                "valid_from": at,
                **values,
            }
        )

    def _effective_or_404(self, parent: Item, component_item_id: int, at: datetime) -> dict[str, Any]:
        if sum(r["component_item_id"] == component_item_id for r in self.calc.effective(parent.id, at)) > 1:
            raise ConflictError("У компонента несколько условных позиций; изменяйте строку по bom_id через configured-bom")
        row = self.calc.effective_row(parent.id, component_item_id, at)  # type: ignore[arg-type]
        if row is None:
            raise NotFoundError(
                f"Компонент {component_item_id} не входит в действующий состав «{parent.name}»"
            )
        return row

    def _remove_effective(self, parent: Item, eff: dict[str, Any], at: datetime) -> Optional[ItemBom]:
        """Убрать компонент из действующего состава.

        Собственная строка закрывается. Если после этого компонент всё ещё
        наследуется от базового изделия — добавляется строка-исключение.
        """
        own = self.boms.get_own_active(parent.id, eff["component_item_id"])  # type: ignore[arg-type]
        if own is not None:
            self.boms.close(own, at)
        if self.calc.effective_row(parent.id, eff["component_item_id"], at) is None:  # type: ignore[arg-type]
            return None
        return self.boms.create(
            {
                "parent_item_id": parent.id,
                "component_item_id": eff["component_item_id"],
                "quantity": Decimal("0"),
                "for_quantity": Decimal("1"),
                "unit_quantity_id": None,
                "is_base": True,
                "is_excluded": True,
                "order_number": eff["order_number"],
                "valid_from": at,
            }
        )

    def _spec_row(self, parent: Item, component_item_id: int, at: datetime) -> BomRowRead:
        self._effective_or_404(parent, component_item_id, at)
        row = next(r for r in self.calc.effective(parent.id, at) if r["component_item_id"] == component_item_id)  # type: ignore[arg-type]
        return BomRowRead(**row)

    # ------------------------------------------------------------ чтение
    def get_spec(self, item_id: int, at: Optional[datetime] = None) -> BomSpecRead:
        """Действующая спецификация изделия (один уровень) на дату."""
        item = self._item(item_id)
        at = at or utcnow()
        rows = [BomRowRead(**r) for r in self.calc.effective(item_id, at)]
        return BomSpecRead(item_id=item_id, item_name=item.name, base_item_id=item.base_item_id, at=at, rows=rows)

    def find_bom(self, item_id: int, at: Optional[datetime] = None) -> BomTreeRead:
        """FIND_BOM: все компоненты на всю глубину вложенности."""
        item = self._item(item_id)
        at = at or utcnow()
        nodes = [BomTreeNode(**rounded(r, "norm", "qty_base")) for r in self.calc.find_bom(item_id, at)]
        return BomTreeRead(item_id=item_id, item_name=item.name, at=at, nodes=nodes)

    def calc_bom(
        self,
        item_id: int,
        quantity: Decimal,
        class_id: Optional[int] = None,
        at: Optional[datetime] = None,
    ) -> NormsRead:
        """CALC_BOM: сводные нормы расхода материалов (заданного класса) на quantity изделий."""
        item = self._item(item_id)
        if quantity <= 0:
            raise BusinessRuleError("Количество изделий должно быть больше нуля")
        if class_id is not None and not self.classifiers.get_by_id(class_id):
            raise NotFoundError(f"Класс изделий {class_id} не найден")
        at = at or utcnow()
        rows = [NormRow(**rounded(r, "total_quantity")) for r in self.calc.calc_bom(item_id, quantity, class_id, at)]
        return NormsRead(item_id=item_id, item_name=item.name, quantity=quantity, class_id=class_id, at=at, rows=rows)

    def history(self, item_id: int) -> list[ChangeRead]:
        """История изменений спецификации изделия: было → стало."""
        self._item(item_id)
        changes = self.changes.by_item(item_id)
        boms = self.boms.get_many(b for c in changes for b in (c.old_bom_id, c.new_bom_id))
        names = self.catalog.item_info(b.component_item_id for b in boms.values())
        types = self.catalog.enum_values(c.change_type_id for c in changes)

        def version(bom_id: Optional[int]) -> Optional[BomVersion]:
            if bom_id is None or bom_id not in boms:
                return None
            b = boms[bom_id]
            return BomVersion(
                bom_id=b.id, component_item_id=b.component_item_id,
                configuration_function_id=b.configuration_function_id,
                component_name=names.get(b.component_item_id, {}).get("component_name", ""),
                quantity=b.quantity, for_quantity=b.for_quantity, is_excluded=b.is_excluded,
                valid_from=b.valid_from, valid_to=b.valid_to,
            )

        result = [
            ChangeRead(
                id=c.id, item_id=c.item_id,
                change_type=types[c.change_type_id].code, change_type_name=types[c.change_type_id].name,
                change_date=c.change_date, reason=c.reason,
                old=version(c.old_bom_id), new=version(c.new_bom_id),
            )
            for c in changes
        ]
        return result

    def get_modifications(self, item_id: int) -> Sequence[Item]:
        self._item(item_id)
        return self.modifications.get_modifications(item_id)

    # ------------------------------------------------------------ редактирование спецификации
    def add_component(self, parent_id: int, data: BomComponentAdd) -> BomRowRead:
        parent = self._item(parent_id)
        self._ensure_can_have_spec(parent)
        component = self._item(data.component_item_id)
        if component.id == parent.id:
            raise BusinessRuleError("Изделие не может входить в собственный состав")
        at = utcnow()
        own = self.boms.get_own_active(parent.id, component.id)  # type: ignore[arg-type]
        if own is None and self.calc.effective_row(parent.id, component.id, at) is not None:  # type: ignore[arg-type]
            raise ConflictError(
                f"Компонент «{component.name}» уже входит в состав (наследуется от базового изделия); "
                "используйте изменение нормы расхода"
            )
        old_id = own.id if own is not None and own.is_excluded else None
        row = self._insert_row(
            parent,
            component,
            {
                "quantity": data.quantity,
                "for_quantity": data.for_quantity,
                "unit_quantity_id": self._resolve_unit(data.unit_quantity_id, component),
                "is_base": data.is_base,
                "is_excluded": False,
                "order_number": data.order_number,
            },
            at,
        )
        self._check_no_cycle(parent, component, at)
        self._register_change(parent.id, "add_component", old_id, row.id, data.reason, at)  # type: ignore[arg-type]
        return self._spec_row(parent, component.id, at)  # type: ignore[arg-type]

    def update_component(self, parent_id: int, component_item_id: int, data: BomComponentUpdate) -> BomRowRead:
        """Изменение нормы расхода. Для унаследованной строки создаётся переопределение в модификации."""
        parent = self._item(parent_id)
        component = self._item(component_item_id)
        at = utcnow()
        eff = self._effective_or_404(parent, component_item_id, at)
        values = {
            "quantity": data.quantity if data.quantity is not None else eff["quantity"],
            "configuration_function_id": eff.get("configuration_function_id"),
            "for_quantity": data.for_quantity if data.for_quantity is not None else eff["for_quantity"],
            "unit_quantity_id": (
                self._resolve_unit(data.unit_quantity_id, component)
                if data.unit_quantity_id is not None
                else eff["unit_quantity_id"]
            ),
            "is_base": data.is_base if data.is_base is not None else eff["is_base"],
            "is_excluded": False,
            "order_number": data.order_number if data.order_number is not None else eff["order_number"],
        }
        if eff["owner_item_id"] == parent.id:
            own = self.boms.get_by_id(eff["bom_id"])
            assert own is not None
            self.boms.close(own, at)
        row = self._insert_row(parent, component, values, at)
        self._register_change(parent.id, "change_quantity", eff["bom_id"], row.id, data.reason, at)  # type: ignore[arg-type]
        return self._spec_row(parent, component_item_id, at)

    def remove_component(self, parent_id: int, component_item_id: int, reason: Optional[str] = None) -> None:
        parent = self._item(parent_id)
        at = utcnow()
        eff = self._effective_or_404(parent, component_item_id, at)
        exclusion = self._remove_effective(parent, eff, at)
        self._register_change(
            parent.id,  # type: ignore[arg-type]
            "remove_component",
            eff["bom_id"],
            exclusion.id if exclusion else None,
            reason,
            at,
        )

    def replace_component(self, parent_id: int, component_item_id: int, data: BomComponentReplace) -> BomRowRead:
        parent = self._item(parent_id)
        new_component = self._item(data.new_component_item_id)
        if new_component.id == parent.id:
            raise BusinessRuleError("Изделие не может входить в собственный состав")
        if new_component.id == component_item_id:
            raise BusinessRuleError("Новый компонент совпадает с заменяемым")
        at = utcnow()
        eff = self._effective_or_404(parent, component_item_id, at)
        if self.calc.effective_row(parent.id, new_component.id, at) is not None:  # type: ignore[arg-type]
            raise ConflictError(f"Компонент «{new_component.name}» уже входит в состав «{parent.name}»")
        self._remove_effective(parent, eff, at)
        row = self._insert_row(
            parent,
            new_component,
            {
                "quantity": data.quantity,
                "for_quantity": data.for_quantity,
                "unit_quantity_id": self._resolve_unit(data.unit_quantity_id, new_component),
                "configuration_function_id": eff.get("configuration_function_id"),
                "is_base": eff["is_base"],
                "is_excluded": False,
                "order_number": eff["order_number"],
            },
            at,
        )
        self._check_no_cycle(parent, new_component, at)
        self._register_change(parent.id, "replace_component", eff["bom_id"], row.id, data.reason, at)  # type: ignore[arg-type]
        return self._spec_row(parent, new_component.id, at)  # type: ignore[arg-type]

    # ------------------------------------------------------------ модификации
    def create_modification(self, base_id: int, data: ModificationCreate) -> Item:
        """CREATE_MODIFICATION: модификация наследует базовую спецификацию и ЕИ базового изделия."""
        base = self._item(base_id)
        at = utcnow()
        existing = {m.number for m in self.modifications.get_modifications(base_id)}
        number = data.number or next_modification_number(base.number, existing)
        if self.items.get_by_number(number):
            raise ConflictError(f"Изделие с обозначением '{number}' уже существует")
        mod = self.items.create(
            {
                "item_class_id": base.item_class_id,
                "item_type_id": base.item_type_id,
                "number": number,
                "article": data.article if data.article is not None else base.article,
                "name": data.name,
                "base_item_id": base.id,
            }
        )
        for uq in self.units.get_by_item(base_id):
            self.units.create(
                {
                    "item_id": mod.id,
                    "unit_simple_id": uq.unit_simple_id,
                    "coefficient": uq.coefficient,
                    "is_base": uq.is_base,
                }
            )
        self._register_change(
            mod.id,  # type: ignore[arg-type]
            "create_modification",
            None,
            None,
            data.reason or f"Модификация изделия {base.number} «{base.name}»",
            at,
        )
        return mod
