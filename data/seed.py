"""Демо-данные «Сервис доставки готовой еды» для показа заданий №4–6.

ВНИМАНИЕ: полностью очищает БД из DATABASE_URL (.env) и заполняет заново.

Запуск:
    python data/seed.py
"""

import os
import sys
import time
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text  # noqa: E402
from sqlmodel import Session  # noqa: E402

from data.technology_seed import seed_technology  # noqa: E402
from src.database.database import SessionLocal  # noqa: E402
from src.models import (  # noqa: E402
    AvailableRoles,
    EnumType,
    EnumValue,
    HoClassParameter,
    HoClassifier,
    Item,
    ItemClassifier,
    Parameter,
    Sxd,
    SxdClassifier,
    SxdRole,
    UnitQuantity,
    UnitSimple,
)
from src.repository.bom_repository import (  # noqa: E402
    ItemBomRepository,
    ItemCatalogRepository,
    ItemChangeRepository,
    ModificationRepository,
)
from src.repository.classifier_repository import ItemClassifierRepository  # noqa: E402
from src.repository.enum_repository import EnumValueRepository  # noqa: E402
from src.repository.item_repository import ItemRepository, UnitQuantityRepository  # noqa: E402
from src.schemas.bom import BomComponentAdd, BomComponentUpdate, ModificationCreate  # noqa: E402
from src.services.bom_service import BomService  # noqa: E402

D = Decimal

# Справочные перечисления (дублируют миграцию 002: TRUNCATE их удаляет)
REFERENCE_ENUMS = {
    ("item_type", "Тип изделия"): [
        ("material", "Материал"),
        ("detail", "Деталь (полуфабрикат)"),
        ("assembly", "Сборочная единица"),
        ("complex", "Комплекс"),
    ],
    ("bom_change_type", "Тип изменения спецификации"): [
        ("add_component", "Добавление компонента"),
        ("change_quantity", "Изменение нормы расхода"),
        ("replace_component", "Замена компонента"),
        ("remove_component", "Удаление компонента"),
        ("create_modification", "Создание модификации"),
    ],
    ("param_type", "Тип параметра"): [
        ("number", "Числовой"),
        ("string", "Строковый"),
        ("enum", "Перечисление"),
        ("date", "Дата"),
    ],
    ("sxd_type", "Тип СХД"): [
        ("legal", "Юридическое лицо"),
        ("individual", "ИП"),
        ("dept", "Подразделение"),
    ],
    ("qualification", "Квалификация"): [
        ("grade_3", "3-й разряд"),
    ],
}

TABLES = (
    "technology_application, technology_template, technology_asset, technology_asset_model, "
    "technology_labor_rate, technology_tool_requirement, technology_input, technology_operation, "
    "work_center, technology_class, "
    "item_change, item_bom, ho_position, position_list, pricelist, pricelist_set, packaging_norm, "
    "packaging, packaging_type, item_batch, unit_quantity, item, doc_parameter_value, "
    "ho_parameter_value, sxd_role_in_ho, document, ho, sxd, available_roles, doc_class_parameter, "
    "ho_class_parameter, parameter, sxd_role, item_classifier, document_classifier, ho_classifier, "
    "sxd_classifier, enum_value, enum_type, unit_simple"
)


def add(session: Session, obj):
    session.add(obj)
    session.flush()
    return obj


def seed(session: Session) -> None:
    session.execute(text(f"TRUNCATE TABLE {TABLES} RESTART IDENTITY CASCADE"))

    # ---------- перечисления
    ev: dict[str, EnumValue] = {}
    for (tcode, tname), values in REFERENCE_ENUMS.items():
        et = add(session, EnumType(code=tcode, name=tname))
        for i, (code, name) in enumerate(values, start=1):
            ev[f"{tcode}.{code}"] = add(session, EnumValue(enum_type_id=et.id, order_number=i, code=code, name=name))

    # ---------- единицы измерения
    kg = add(session, UnitSimple(code="KGM", name="Килограмм", cond_symbol_1="кг", cond_symbol_2="kg"))
    g = add(session, UnitSimple(code="GRM", name="Грамм", cond_symbol_1="г", cond_symbol_2="g",
                                base_unit_id=kg.id, coefficient=D("0.001")))
    l = add(session, UnitSimple(code="LTR", name="Литр", cond_symbol_1="л", cond_symbol_2="l"))
    ml = add(session, UnitSimple(code="MLT", name="Миллилитр", cond_symbol_1="мл", cond_symbol_2="ml",
                                 base_unit_id=l.id, coefficient=D("0.001")))
    pcs = add(session, UnitSimple(code="PCE", name="Штука", cond_symbol_1="шт", cond_symbol_2="pcs"))

    # ---------- классификатор изделий
    cls: dict[str, ItemClassifier] = {}

    def c(name, parent=None, number=None):
        cls[name] = add(session, ItemClassifier(name=name, number=number,
                                                parent_id=cls[parent].id if parent else None))

    c("Продукция и сырьё", number="1")
    c("Сырьё", "Продукция и сырьё", "1.1")
    c("Мука и крупы", "Сырьё", "1.1.1")
    c("Молочные продукты", "Сырьё", "1.1.2")
    c("Сыры", "Молочные продукты", "1.1.2.1")
    c("Овощи", "Сырьё", "1.1.3")
    c("Специи и зелень", "Сырьё", "1.1.4")
    c("Масла и вода", "Сырьё", "1.1.5")
    c("Мясо и птица", "Сырьё", "1.1.6")
    c("Упаковка", "Продукция и сырьё", "1.2")
    c("Полуфабрикаты", "Продукция и сырьё", "1.3")
    c("Блюда", "Продукция и сырьё", "1.4")
    c("Пицца", "Блюда", "1.4.1")
    c("Салаты", "Блюда", "1.4.2")
    c("Наборы (комбо)", "Продукция и сырьё", "1.5")

    # ---------- изделия
    items: dict[str, Item] = {}
    uq: dict[tuple[str, str], UnitQuantity] = {}

    def it(key, number, type_code, cls_name, base=kg, extra=None):
        items[key] = add(session, Item(number=number, name=key, item_type_id=ev[f"item_type.{type_code}"].id,
                                       item_class_id=cls[cls_name].id))
        uq[(key, base.cond_symbol_1)] = add(session, UnitQuantity(item_id=items[key].id, unit_simple_id=base.id,
                                                                   is_base=True))
        for unit, coef in (extra or []):
            uq[(key, unit.cond_symbol_1)] = add(session, UnitQuantity(item_id=items[key].id, unit_simple_id=unit.id,
                                                                       coefficient=D(coef)))

    grams = [(g, "0.001")]
    it("Мука пшеничная в/с", "RM-001", "material", "Мука и крупы")
    it("Вода питьевая", "RM-002", "material", "Масла и вода", base=l, extra=[(ml, "0.001")])
    it("Дрожжи сухие", "RM-003", "material", "Мука и крупы", extra=grams)
    it("Масло оливковое", "RM-004", "material", "Масла и вода", base=l, extra=[(ml, "0.001")])
    it("Соль", "RM-005", "material", "Специи и зелень", extra=grams)
    it("Моцарелла", "RM-010", "material", "Сыры", extra=grams)
    it("Пармезан", "RM-011", "material", "Сыры", extra=grams)
    it("Томаты", "RM-020", "material", "Овощи")
    it("Халапеньо", "RM-021", "material", "Овощи", extra=grams)
    it("Салат романо", "RM-022", "material", "Овощи", extra=grams)
    it("Базилик свежий", "RM-030", "material", "Специи и зелень", extra=grams)
    it("Филе куриное", "RM-040", "material", "Мясо и птица", extra=grams)
    it("Коробка для пиццы 30 см", "PK-001", "material", "Упаковка", base=pcs)
    it("Контейнер для салата", "PK-002", "material", "Упаковка", base=pcs)
    it("Тесто для пиццы", "SF-001", "detail", "Полуфабрикаты")
    it("Соус томатный", "SF-002", "detail", "Полуфабрикаты")
    it("Соус цезарь", "SF-003", "detail", "Полуфабрикаты")
    it("Пицца Маргарита 30 см", "PZ-001", "assembly", "Пицца", base=pcs)
    it("Салат Цезарь с курицей", "SL-001", "assembly", "Салаты", base=pcs)
    it("Комбо «Обед на двоих»", "CB-001", "complex", "Наборы (комбо)", base=pcs)
    session.flush()

    # ---------- спецификации (через сервис, чтобы фиксировалась история)
    svc = BomService(
        items=ItemRepository(session), boms=ItemBomRepository(session), changes=ItemChangeRepository(session),
        modifications=ModificationRepository(session), enum_values=EnumValueRepository(session),
        units=UnitQuantityRepository(session), classifiers=ItemClassifierRepository(session),
        catalog=ItemCatalogRepository(session),
    )

    def bom(parent, comp, qty, unit=None, for_qty="1", order=0, is_base=True, reason="Первичное заполнение"):
        svc.add_component(items[parent].id, BomComponentAdd(
            component_item_id=items[comp].id, quantity=D(qty), for_quantity=D(for_qty),
            unit_quantity_id=uq[(comp, unit)].id if unit else None,
            order_number=order, is_base=is_base, reason=reason,
        ))

    # Тесто: норма на 10 кг замеса
    bom("Тесто для пиццы", "Мука пшеничная в/с", "6", for_qty="10", order=1)
    bom("Тесто для пиццы", "Вода питьевая", "3.6", for_qty="10", order=2)
    bom("Тесто для пиццы", "Масло оливковое", "200", unit="мл", for_qty="10", order=3)
    bom("Тесто для пиццы", "Дрожжи сухие", "100", unit="г", for_qty="10", order=4)
    bom("Тесто для пиццы", "Соль", "150", unit="г", for_qty="10", order=5)
    # Соусы: норма на 1 кг
    bom("Соус томатный", "Томаты", "1.2", order=1)
    bom("Соус томатный", "Соль", "10", unit="г", order=2)
    bom("Соус томатный", "Базилик свежий", "10", unit="г", order=3)
    bom("Соус цезарь", "Масло оливковое", "0.5", order=1)
    bom("Соус цезарь", "Пармезан", "150", unit="г", order=2)
    # Блюда: норма на 1 шт
    bom("Пицца Маргарита 30 см", "Тесто для пиццы", "0.25", order=1)
    bom("Пицца Маргарита 30 см", "Соус томатный", "0.08", order=2)
    bom("Пицца Маргарита 30 см", "Моцарелла", "120", unit="г", order=3)
    bom("Пицца Маргарита 30 см", "Базилик свежий", "5", unit="г", order=4)
    bom("Пицца Маргарита 30 см", "Коробка для пиццы 30 см", "1", order=5, is_base=False)
    bom("Салат Цезарь с курицей", "Салат романо", "120", unit="г", order=1)
    bom("Салат Цезарь с курицей", "Филе куриное", "100", unit="г", order=2)
    bom("Салат Цезарь с курицей", "Соус цезарь", "0.04", order=3)
    bom("Салат Цезарь с курицей", "Пармезан", "15", unit="г", order=4)
    bom("Салат Цезарь с курицей", "Контейнер для салата", "1", order=5)
    # Комбо: 2 пиццы + 1 салат
    bom("Комбо «Обед на двоих»", "Пицца Маргарита 30 см", "2", order=1)
    bom("Комбо «Обед на двоих»", "Салат Цезарь с курицей", "1", order=2)

    time.sleep(0.01)  # чтобы версии «до» и «после» отличались по времени
    svc.update_component(items["Пицца Маргарита 30 см"].id, items["Моцарелла"].id,
                         BomComponentUpdate(quantity=D("130"), reason="Увеличили сыр по отзывам клиентов"))

    # Модификация: «Маргарита острая»
    mod = svc.create_modification(items["Пицца Маргарита 30 см"].id, ModificationCreate(
        name="Пицца Маргарита острая 30 см", number="PZ-001-01", reason="Сезонное меню"))
    svc.update_component(mod.id, items["Моцарелла"].id,
                         BomComponentUpdate(quantity=D("150"), reason="В острой версии больше сыра"))
    svc.add_component(mod.id, BomComponentAdd(component_item_id=items["Халапеньо"].id, quantity=D("30"),
                                              unit_quantity_id=uq[("Халапеньо", "г")].id, order_number=6,
                                              reason="Острый перец"))
    svc.remove_component(mod.id, items["Базилик свежий"].id, reason="Базилик не сочетается с халапеньо")
    svc.add_component(mod.id, BomComponentAdd(component_item_id=items["Коробка для пиццы 30 см"].id,
                                              quantity=D("1"), order_number=7, reason="Своя упаковка"))
    items[mod.name] = mod

    # ---------- минимум для задания №4 (ХО «Доставка заказа»)
    sxd_cls = add(session, SxdClassifier(name="Контрагенты", code="contractors"))
    add(session, Sxd(name="ООО «Вкусно и быстро» (кухня)", entity_type_id=ev["sxd_type.legal"].id,
                     sxd_class_id=sxd_cls.id, okpo="12345678"))
    add(session, Sxd(name="ИП Иванов (курьер)", entity_type_id=ev["sxd_type.individual"].id,
                     sxd_class_id=sxd_cls.id))
    ho_root = add(session, HoClassifier(name="Хозяйственные операции", code="ho"))
    delivery = add(session, HoClassifier(name="Доставка заказа", code="delivery", parent_id=ho_root.id))
    p_sum = add(session, Parameter(code="order_sum", name="Сумма заказа", param_type_id=ev["param_type.number"].id))
    add(session, HoClassParameter(ho_type_id=delivery.id, parameter_id=p_sum.id, min_value=D("0")))
    for role_name in ("Отправитель", "Курьер", "Получатель"):
        role = add(session, SxdRole(name=role_name))
        add(session, AvailableRoles(ho_type_id=delivery.id, role_id=role.id, min_count=1, max_count=1,
                                    is_required=True))
    kitchen = add(session, Sxd(name="Горячий цех", entity_type_id=ev["sxd_type.dept"].id))
    seed_technology(session, items, uq, ev, kitchen.id)
    _ = date.today()


def main() -> None:
    with SessionLocal() as session:
        seed(session)
        session.commit()
    print("✓ Демо-данные «Сервис доставки готовой еды» загружены")


if __name__ == "__main__":
    main()
