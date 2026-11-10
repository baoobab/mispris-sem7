"""Демонстрационные маршруты для номенклатуры из data.seed."""

from decimal import Decimal

from src.models import Pricelist, PricelistSet, TechnologyAssetModel
from src.repository.technology_repository import TechnologyRepository
from src.schemas.technology import (
    AssetCreate, ClassCreate, OperationCreate, TemplateApply, TemplateCreate, WorkCenterCreate,
)
from src.services.technology_service import TechnologyService


def seed_technology(session, items, units, enums, department_id):
    service = TechnologyService(TechnologyRepository(session))

    def add(row):
        return service.repo.save(row)

    operation_class = service.save_class(ClassCreate(kind="operation", code="cooking", name="Приготовление"))
    packing_class = service.save_class(ClassCreate(kind="operation", code="packing", name="Фасовка"))
    profession = service.save_class(ClassCreate(kind="profession", code="cook", name="Повар"))
    center_class = service.save_class(ClassCreate(kind="work_center", code="kitchen", name="Производственная кухня"))
    center = service.save_work_center(WorkCenterCreate(
        code="KITCHEN-1", name="Горячий цех", class_id=center_class.id, sxd_id=department_id,
    ))
    oven = add(TechnologyAssetModel(code="OVEN", name="Печь для пиццы", kind="equipment"))
    tray = add(TechnologyAssetModel(code="TRAY", name="Противень", kind="fixture"))
    for inventory, model in (("OV-001", oven), ("TR-001", tray)):
        service.save_asset(AssetCreate(inventory_number=inventory, model_id=model.id, work_center_id=center.id))

    qualification = enums["qualification.grade_3"]
    service.put_rate(profession.id, qualification.id, Decimal("360"))
    price_set = add(PricelistSet())
    operations = {}
    for index, (name, item) in enumerate(items.items(), start=1):
        if item.item_type_id != enums["item_type.material"].id:
            continue
        operations[name] = service.save_operation(item.id, OperationCreate(
            number=10, name="Закупка", kind="purchase", is_output=True,
        ))
        add(Pricelist(pricelist_set_id=price_set.id, item_id=item.id, price=Decimal(25 + 5 * index)))

    production = dict(
        kind="production", work_center_id=center.id, profession_id=profession.id, qualification_id=qualification.id,
    )

    def from_bom(name, description, minutes, class_id=operation_class.id):
        item = items[name]
        operations[name] = service.save_operation(item.id, OperationCreate(
            **production, class_id=class_id, number=10, name=description, is_output=True,
            setup_minutes=3, piece_minutes=minutes,
        ))
        service.import_bom(item.id, operations[name].id, None)

    from_bom("Тесто для пиццы", "Замес теста", 8)
    from_bom("Соус томатный", "Варка соуса", 10)
    from_bom("Соус цезарь", "Подготовка соуса", 6)

    def norm(key, value):
        return {"input_key": key, "quantity": {"constant": value}}

    template = service.create_template(TemplateCreate(
        code="PIZZA-30", name="Выпечка пиццы 30 см",
        definition={"parameters": ["cheese_g", "topping_g", "baking_minutes"], "steps": [
            dict(production, class_id=operation_class.id, number=10, name="Пицца после выпечки",
                 setup_minutes={"constant": 5}, piece_minutes={"factors": {"baking_minutes": 1}},
                 tools={oven.id: 1, tray.id: 1}, inputs=[
                     norm("dough", "0.25"), norm("sauce", "0.08"),
                     {"input_key": "cheese", "quantity": {"factors": {"cheese_g": 1}}},
                     {"input_key": "topping", "quantity": {"factors": {"topping_g": 1}}},
                 ]),
            dict(production, class_id=packing_class.id, number=20, name="Пицца после упаковки", is_output=True,
                 piece_minutes={"constant": 1}, inputs=[
                     {"input_number": 10, "quantity": {"constant": 1}}, norm("box", 1),
                 ]),
        ]},
    ))

    def bind(name, symbol=None):
        return {"operation_id": operations[name].id, "unit_quantity_id": units[(name, symbol)].id if symbol else None}

    base = items["Пицца Маргарита 30 см"]
    spicy = items["Пицца Маргарита острая 30 см"]
    for item, topping, cheese_g, topping_g, baking_minutes in (
        (base, "Базилик свежий", 130, 5, 7),
        (spicy, "Халапеньо", 150, 30, 8),
    ):
        service.apply_template(item.id, template.id, TemplateApply(
            parameters=dict(cheese_g=cheese_g, topping_g=topping_g, baking_minutes=baking_minutes),
            resources=dict(
                dough=bind("Тесто для пиццы"), sauce=bind("Соус томатный"), cheese=bind("Моцарелла", "г"),
                topping=bind(topping, "г"), box=bind("Коробка для пиццы 30 см"),
            ),
        ))
    from_bom("Салат Цезарь с курицей", "Сборка салата", 5)
    from_bom("Комбо «Обед на двоих»", "Комплектация заказа", 1, class_id=packing_class.id)
