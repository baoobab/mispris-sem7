"""Расчёты по материальной спецификации (задание №5).

    effective  — действующая спецификация изделия на момент времени (один уровень) с учётом модификаций
    find_bom   — FIND_BOM: состав изделия на всю глубину вложенности с нормой на 1 изделие
    calc_bom   — CALC_BOM: сводные нормы расхода материалов (заданного класса) на заданное количество
    has_cycle  — проверка цикла в составе изделия и его модификаций

Норма компонента на единицу корневого изделия — произведение норм по пути от корня:
расход позиции × коэффициент ЕИ к базовой / количество изделия, на которое дан расход.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from src.repository.bom_repository import ItemBomRepository, ItemCatalogRepository

MAX_BASE_CHAIN = 32   # глубина цепочки «модификация → базовое изделие»
MAX_DEPTH = 100       # глубина вложенности состава
ONE = Decimal("1")


class BomCalculator:
    def __init__(self, boms: ItemBomRepository, catalog: ItemCatalogRepository) -> None:
        self.boms = boms
        self.catalog = catalog

    # ------------------------------------------------------------ действующая спецификация
    def _base_chain(self, item_id: int) -> list[int]:
        """[изделие, его базовое, базовое базового, ...]."""
        chain = [item_id]
        while len(chain) < MAX_BASE_CHAIN:
            base = self.catalog.base_item_id(chain[-1])
            if base is None or base in chain:
                break
            chain.append(base)
        return chain

    def _effective_raw(self, item_id: int, at: datetime, include_excluded: bool = False) -> list[dict[str, Any]]:
        """Собственные позиции изделия + позиции базовой спецификации (флаг базы) по цепочке
        базовых изделий; для каждого компонента берётся ближайшая к изделию версия."""
        chain = self._base_chain(item_id)
        level = {iid: lvl for lvl, iid in enumerate(chain)}
        chosen: dict[tuple[int, Optional[int]], tuple[int, Any]] = {}
        for row in self.boms.rows_at(chain, at):
            lvl = level[row.parent_item_id]
            if lvl > 0 and not row.is_base:
                continue  # строка без флага базы действует только у своего изделия
            key = (row.component_item_id, getattr(row, "configuration_function_id", None))
            best = chosen.get(key)
            if best is None or lvl < best[0]:
                chosen[key] = (lvl, row)
        result = []
        for lvl, row in chosen.values():
            if row.is_excluded and not include_excluded:
                continue
            result.append({
                "bom_id": row.id,
                "configuration_function_id": getattr(row, "configuration_function_id", None),
                "owner_item_id": row.parent_item_id,
                "inherit_level": lvl,
                "inherited": lvl > 0,
                "component_item_id": row.component_item_id,
                "quantity": row.quantity,
                "for_quantity": row.for_quantity,
                "unit_quantity_id": row.unit_quantity_id,
                "is_base": row.is_base,
                "is_excluded": row.is_excluded,
                "order_number": row.order_number,
            })
        result.sort(key=lambda r: (r["order_number"], r["component_item_id"]))
        return result

    def _with_details(self, rows: list[dict[str, Any]], key: str = "component_item_id") -> list[dict[str, Any]]:
        info = self.catalog.item_info(r[key] for r in rows)
        units = self.catalog.unit_info(r.get("unit_quantity_id") for r in rows)
        for r in rows:
            r.update(info.get(r[key], {}))
            if "unit_quantity_id" in r:
                r["unit_symbol"] = units.get(r["unit_quantity_id"], (None, None))[1]
        return rows

    def effective(self, item_id: int, at: datetime, include_excluded: bool = False) -> list[dict[str, Any]]:
        return self._with_details(self._effective_raw(item_id, at, include_excluded))

    def effective_row(self, item_id: int, component_item_id: int, at: datetime) -> Optional[dict[str, Any]]:
        for row in self._effective_raw(item_id, at):
            if row["component_item_id"] == component_item_id:
                return row
        return None

    # ------------------------------------------------------------ FIND_BOM
    def find_bom(self, item_id: int, at: datetime) -> list[dict[str, Any]]:
        """Обход дерева состава в глубину с накоплением нормы; повтор компонента на пути — цикл."""
        cache: dict[int, list[dict[str, Any]]] = {}
        nodes: list[dict[str, Any]] = []

        def spec(iid: int) -> list[dict[str, Any]]:
            if iid not in cache:
                cache[iid] = self._effective_raw(iid, at)
            return cache[iid]

        def walk(parent_id: int, path: list[int], parent_norm: Decimal, lvl: int) -> None:
            rows = spec(parent_id)
            units = self.catalog.unit_info(r["unit_quantity_id"] for r in rows)
            for r in rows:
                coefficient = units.get(r["unit_quantity_id"], (ONE, None))[0] or ONE
                qty_base = r["quantity"] * coefficient
                norm = parent_norm * qty_base / r["for_quantity"]
                comp = r["component_item_id"]
                is_cycle = comp in path
                nodes.append({
                    "lvl": lvl,
                    "path": path + [comp],
                    "parent_item_id": parent_id,
                    "component_item_id": comp,
                    "bom_id": r["bom_id"],
                    "owner_item_id": r["owner_item_id"],
                    "inherited": r["owner_item_id"] != parent_id,
                    "quantity": r["quantity"],
                    "for_quantity": r["for_quantity"],
                    "unit_quantity_id": r["unit_quantity_id"],
                    "coefficient": coefficient,
                    "qty_base": qty_base,
                    "norm": norm,
                    "is_cycle": is_cycle,
                })
                if not is_cycle and lvl < MAX_DEPTH:
                    walk(comp, path + [comp], norm, lvl + 1)

        walk(item_id, [item_id], ONE, 1)
        return self._with_details(nodes)

    # ------------------------------------------------------------ CALC_BOM
    def _class_subtree(self, class_id: int) -> set[int]:
        result, stack = set(), [class_id]
        while stack:
            cid = stack.pop()
            if cid in result:
                continue
            result.add(cid)
            stack.extend(self.catalog.class_children(cid))
        return result

    def calc_bom(self, item_id: int, quantity: Decimal, class_id: Optional[int], at: datetime) -> list[dict[str, Any]]:
        """Без класса — суммируются материалы (компоненты без собственного состава).
        С классом — компоненты класса и его подклассов; на каждом пути берётся первый компонент
        класса, поэтому сырьё внутри полуфабриката того же класса не учитывается дважды."""
        nodes = [n for n in self.find_bom(item_id, at) if not n["is_cycle"]]
        info = self.catalog.item_info(n["component_item_id"] for n in nodes)
        totals: dict[int, Decimal] = {}
        if class_id is None:
            has_spec = {iid: bool(self._effective_raw(iid, at)) for iid in {n["component_item_id"] for n in nodes}}
            selected = [n for n in nodes if not has_spec[n["component_item_id"]]]
        else:
            subtree = self._class_subtree(class_id)

            def in_class(iid: int) -> bool:
                return info.get(iid, {}).get("class_id") in subtree

            selected = [n for n in nodes
                        if in_class(n["component_item_id"]) and not any(in_class(a) for a in n["path"][1:-1])]
        for n in selected:
            totals[n["component_item_id"]] = totals.get(n["component_item_id"], Decimal(0)) + n["norm"]
        rows = [{"component_item_id": iid, "total_quantity": total * quantity, **info.get(iid, {})}
                for iid, total in totals.items()]
        rows.sort(key=lambda r: (r.get("class_name") is None, r.get("class_name") or "", r.get("component_name") or ""))
        return rows

    # ------------------------------------------------------------ контроль циклов
    def has_cycle(self, item_id: int, at: datetime) -> bool:
        """Цикл ищется в составе изделия и всех его модификаций (они наследуют его спецификацию)."""
        affected, stack = [], [item_id]
        while stack:
            iid = stack.pop()
            if iid in affected:
                continue
            affected.append(iid)
            stack.extend(self.catalog.modification_ids(iid))
        return any(n["is_cycle"] for iid in affected for n in self.find_bom(iid, at))
