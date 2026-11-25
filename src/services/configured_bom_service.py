from decimal import Decimal

from src.core.errors import BusinessRuleError, ConflictError
from src.models.bom import ItemBom
from src.models.configured_bom import BomConjunction, BomFunction, BomPredicate
from src.models.configuration import ConfigurationFunction, ItemConfiguration, VariantParameterValue
from src.models.enums import EnumValue
from src.models.items import Item
from src.models.parameters import Parameter
from src.models.rule_structure import RuleOperator
from src.repository.bom_repository import ItemCatalogRepository
from src.services.bom_service import utcnow
from src.services.configuration_service import ConfigurationService


class ConfiguredBomService(ConfigurationService):
    def functions(self):
        return [self.function(row.function_id) for row in self.repo.rows(BomFunction)]

    def function(self, function_id):
        self.require(BomFunction, function_id)
        header = self.require(ConfigurationFunction, function_id)
        groups = []
        for group in sorted(self.repo.rows(BomConjunction, function_id=function_id), key=lambda r: r.number):
            predicates = []
            for row in sorted(self.repo.rows(BomPredicate, function_id=function_id,
                                            conjunction_number=group.number), key=lambda r: r.number):
                predicates.append({"parameter_id": row.parameter_id,
                                   "operator": self.require(RuleOperator, row.operator_id).code,
                                   "value_number": row.value_number, "value_text": row.value_text,
                                   "enum_value_id": row.enum_value_id})
            groups.append(predicates)
        return {"id": header.id, "code": header.code, "name": header.name, "conjunctions": groups}

    def validate_predicate(self, predicate):
        parameter = self.require(Parameter, predicate.parameter_id)
        typ = self.parameter_type(parameter)
        if typ in ("int", "real"):
            if predicate.value_number is None:
                raise BusinessRuleError("Числовому параметру нужно value_number")
            if typ == "int" and predicate.value_number != predicate.value_number.to_integral_value():
                raise BusinessRuleError("Значение целого параметра должно быть целым")
        elif typ == "str":
            if predicate.value_text is None:
                raise BusinessRuleError("Строковому параметру нужно value_text")
        else:
            if predicate.enum_value_id is None:
                raise BusinessRuleError("Перечислению нужна ссылка enum_value_id")
            value = self.require(EnumValue, predicate.enum_value_id)
            if value.enum_type_id != parameter.enum_type_id:
                raise BusinessRuleError("Значение принадлежит другому перечислению")
            if predicate.operator not in ("eq", "ne"):
                raise BusinessRuleError("Для перечислений поддерживаются eq и ne")
        return self.repo.rows(RuleOperator, code=predicate.operator)[0].id

    def write_function(self, data, function_id=None):
        self.repo.lock()
        operators = [[self.validate_predicate(p) for p in group] for group in data.conjunctions]
        if sum(map(len, data.conjunctions)) > 1000:
            raise BusinessRuleError("Слишком много предикатов")
        if function_id is None:
            header = self.repo.save(ConfigurationFunction(code=data.code, name=data.name))
            function_id = header.id
            self.repo.save(BomFunction(function_id=function_id))
        else:
            self.require(BomFunction, function_id)
            header = self.require(ConfigurationFunction, function_id)
            header.code, header.name = data.code, data.name
            self.repo.save(header)
            for row in self.repo.rows(BomPredicate, function_id=function_id):
                self.repo.delete(row)
            for row in self.repo.rows(BomConjunction, function_id=function_id):
                self.repo.delete(row)
        for n, group in enumerate(data.conjunctions, 1):
            self.repo.save(BomConjunction(function_id=function_id, number=n))
            for m, predicate in enumerate(group, 1):
                self.repo.save(BomPredicate(function_id=function_id, conjunction_number=n, number=m,
                                           operator_id=operators[n-1][m-1],
                                           **predicate.model_dump(exclude={"operator"})))
        return self.function(function_id)

    def delete_function(self, function_id):
        self.repo.lock()
        self.require(BomFunction, function_id)
        # Исторические версии тоже сохраняют связь с функцией; FK защищает удаление.
        if self.repo.rows(ItemBom, configuration_function_id=function_id):
            raise ConflictError("Функция используется в спецификации или её истории")
        from src.models.rule_structure import RuleExpression
        if self.repo.rows(RuleExpression, function_id=function_id):
            raise ConflictError("Функция вызывается другим правилом")
        for model in (BomPredicate, BomConjunction):
            for row in self.repo.rows(model, function_id=function_id):
                self.repo.delete(row)
        self.repo.delete(self.require(BomFunction, function_id))
        self.repo.delete(self.require(ConfigurationFunction, function_id))

    def set_condition(self, item_id, component_id, data, bom_service):
        self.repo.lock()
        if data.function_id is not None:
            self.require(BomFunction, data.function_id)
        own = [r for r in self.repo.rows(ItemBom, parent_item_id=item_id, component_item_id=component_id)
               if r.valid_to is None]
        if len(own) > 1:
            raise ConflictError("Есть альтернативные позиции; изменяйте их по bom_id")
        # Смена условия — новая версия существующей позиции и запись в item_change.
        from src.schemas.bom import BomComponentUpdate
        current = bom_service._effective_or_404(bom_service._item(item_id), component_id, utcnow())
        result = bom_service.update_component(item_id, component_id, BomComponentUpdate(
            quantity=current["quantity"], reason=data.reason or "Изменено условие включения позиции"))
        row = self.require(ItemBom, result.bom_id)
        row.configuration_function_id = data.function_id
        self.repo.save(row)
        return {"bom_id": row.id, "function_id": row.configuration_function_id}

    def write_position(self, item_id, data, bom_service, bom_id=None):
        """Варианты норм одного компонента — отдельные строки имеющегося item_bom."""
        self.repo.lock()
        parent = bom_service._item(item_id)
        bom_service._ensure_can_have_spec(parent)
        component = bom_service._item(data.component_item_id)
        if parent.id == component.id:
            raise BusinessRuleError("Изделие не может входить в собственный состав")
        if data.function_id is not None:
            self.require(BomFunction, data.function_id)
        at = utcnow()
        old = None
        if bom_id is not None:
            old = self.require(ItemBom, bom_id)
            if old.parent_item_id != item_id or old.valid_to is not None:
                raise ConflictError("Позиция не является действующей собственной строкой изделия")
            bom_service.boms.close(old, at)
        row = bom_service.boms.create({
            **data.model_dump(exclude={"function_id", "reason"}),
            "parent_item_id": item_id, "configuration_function_id": data.function_id,
            "unit_quantity_id": bom_service._resolve_unit(data.unit_quantity_id, component),
            "valid_from": at,
        })
        bom_service._check_no_cycle(parent, component, at)
        bom_service._register_change(item_id, "change_quantity" if old else "add_component",
                                     old.id if old else None, row.id, data.reason, at)
        return row

    def delete_position(self, item_id, bom_id, bom_service):
        self.repo.lock()
        row = self.require(ItemBom, bom_id)
        if row.parent_item_id != item_id or row.valid_to is not None:
            raise ConflictError("Позиция не является действующей собственной строкой изделия")
        at = utcnow()
        bom_service.boms.close(row, at)
        bom_service._register_change(item_id, "remove_component", row.id, None,
                                     "Удалена позиция конфигурируемой спецификации", at)

    def prepare_values(self, item_id, supplied=None):
        item = self.require(Item, item_id)
        meta = self.repo.get(ItemConfiguration, item_id)
        if meta and meta.kind == "variant":
            if supplied:
                raise BusinessRuleError("Для сохранённого варианта используются его сохранённые параметры")
            values = {self.require(Parameter, row.parameter_id).code: row.value
                      for row in self.repo.rows(VariantParameterValue, item_id=item_id)}
            source = meta.template_id
        elif meta and meta.kind == "template":
            source, values = item_id, supplied or {}
        else:
            if supplied:
                raise BusinessRuleError("Для простого изделия параметры конфигурации не задаются")
            return item.id, {}
        checked = self.check_constraints(source, values)
        if not checked["valid"]:
            raise BusinessRuleError("Нарушены ограничения: " + "; ".join(checked["violations"]))
        specs, validated = self.validated_values(source, values)
        return source, {row["parameter_id"]: validated[row["code"]] for row in specs if row["code"] in validated}

    def build(self, item_id, quantity=Decimal(1), at=None, values=None):
        source, parameters = self.prepare_values(item_id, values)
        at = at or utcnow()
        if at.tzinfo is None:
            raise BusinessRuleError("Укажите часовой пояс даты спецификации")
        raw = self.repo.tree(item_id, parameters, at)
        catalog = ItemCatalogRepository(self.repo.session)
        info = catalog.item_info(r["component_item_id"] for r in raw)
        nodes = [{**r, **{k: info[r["component_item_id"]][k] for k in (
            "component_name", "component_number", "base_unit_symbol")},
                  "total_quantity": r["norm"] * quantity} for r in raw]
        norms = [{**r, **{k: info[r["component_item_id"]][k] for k in (
            "component_name", "component_number", "base_unit_symbol")}}
                 for r in self.repo.norms(item_id, parameters, at, quantity)]
        return {"item_id": item_id, "source_item_id": source, "at": at,
                "quantity": quantity, "nodes": nodes, "norms": norms}
