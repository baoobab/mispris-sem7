from decimal import Decimal as D

import pytest
from sqlmodel import select

from src.models import EnumType, EnumValue, Pricelist, PricelistSet, Sxd
from tests.helpers import Catalog


def call(client, method, url, status=200, **kwargs):
    response = client.request(method, url, **kwargs)
    assert response.status_code == status, response.text
    return response.json() if status != 204 else None


def route(item):
    return f"/api/items/{item.id}/technology"


def operation(client, item, number, *, production=None, output=False, setup=0, piece=0):
    return call(client, "POST", route(item) + "/operations", 201, json=dict(
        number=number, name=f"Операция {number}", is_output=output,
        **(dict(production, setup_minutes=setup, piece_minutes=piece) if production else {"kind": "purchase"}),
    ))["id"]


def connect(client, item, out_id, in_id, quantity, for_quantity=1, unit=None, status=200):
    return call(client, "PUT", route(item) + f"/operations/{out_id}/inputs/{in_id}", status, json=dict(
        quantity=quantity, for_quantity=for_quantity, unit_quantity_id=unit,
    ))


@pytest.fixture()
def technology(client, session):
    qual_type = session.exec(select(EnumType).where(EnumType.code == "qualification")).one()
    sxd_type = EnumType(code="sxd_type", name="Тип СХД")
    session.add(sxd_type)
    session.flush()
    department_type = EnumValue(enum_type_id=sxd_type.id, order_number=1, code="dept", name="Подразделение")
    qual = EnumValue(enum_type_id=qual_type.id, order_number=3, code="grade_3", name="Третий разряд")
    session.add_all([department_type, qual])
    session.flush()
    sxd = Sxd(name="Кухня", entity_type_id=department_type.id)
    session.add(sxd)
    session.flush()
    classes = {
        kind: call(client, "POST", "/api/technology/classes", 201, json={"kind": kind, "code": kind, "name": name})["id"]
        for kind, name in (("operation", "Приготовление"), ("profession", "Повар"), ("work_center", "Кухня"))
    }
    center = call(client, "POST", "/api/technology/work-centers", 201, json={
        "code": "kitchen", "name": "Рабочий центр", "class_id": classes["work_center"], "sxd_id": sxd.id,
    })
    return Catalog(session), dict(
        kind="production", class_id=classes["operation"], work_center_id=center["id"],
        profession_id=classes["profession"], qualification_id=qual.id,
    )


def test_nested_route_norms_and_cost(client, session, technology):
    catalog, production = technology
    product = catalog.item("Блюдо", "assembly", base_unit="шт")
    batch = catalog.item("Заготовка", "detail")
    flour = catalog.item("Мука", "material", extra_units={"г": "0.001"})
    grams = catalog.uq[("Мука", "г")].id
    raw = operation(client, flour, 10, output=True)
    prep = operation(client, batch, 10, production=production, output=True, setup=6, piece="1.5")
    cook = operation(client, product, 10, production=production, setup=4, piece=2)
    pack = operation(client, product, 30, production=production, output=True, setup=10, piece=3)
    connect(client, batch, prep, raw, 250, 2, grams)
    connect(client, product, cook, prep, 1, 2)
    connect(client, product, cook, raw, 100, unit=grams)
    connect(client, product, pack, prep, 3, 2)
    connect(client, product, pack, cook, 2)

    model = call(client, "POST", "/api/technology/asset-models", 201, json={
        "code": "TRAY", "name": "Противень", "kind": "fixture",
    })
    asset = call(client, "POST", "/api/technology/assets", 201, json={
        "inventory_number": "IN-1", "model_id": model["id"], "work_center_id": production["work_center_id"],
    })
    assert call(client, "GET", "/api/technology/assets", params={
        "work_center_id": production["work_center_id"],
    }) == [asset]
    tool = call(client, "PUT", route(product) + f"/operations/{cook}/tools/{model['id']}", json={"quantity": 2})

    data = call(client, "GET", route(product) + "/route")
    assert data["output_operation_id"] == pack
    assert [op["id"] for op in data["operations"]] == [raw, prep, cook, pack]
    assert {op["id"]: op["depth"] for op in data["operations"]} == {pack: 0, cook: 1, prep: 1, raw: 2}
    assert len(data["inputs"]) == 5
    assert data["tools"] == [tool]
    direct = call(client, "GET", route(product) + f"/operations/{pack}/materials", params={"quantity": 4})
    assert {r["in_operation_id"]: (r["item_name"], D(r["quantity"]), r["unit_symbol"]) for r in direct} == {
        cook: ("Блюдо", D(8), "шт"),
        prep: ("Заготовка", D(6), "кг"),
    }
    materials = call(client, "GET", route(product) + "/materials", params={"quantity": 4})
    assert [
        (r["item_id"], r["item_name"], r["unit_quantity_id"], D(r["quantity"]), r["unit_symbol"])
        for r in materials
    ] == [
        (flour.id, "Мука", catalog.uq[("Мука", "кг")].id, D("2.05"), "кг"),
    ]
    labor, = call(client, "GET", route(product) + "/labor", params={"quantity": 4})
    assert labor["profession_name"] == "Повар"
    assert [D(labor[key]) for key in ("setup_minutes", "piece_minutes", "total_minutes")] == [D(20), D(43), D(63)]

    price_set = PricelistSet()
    session.add(price_set)
    session.flush()
    params = {"quantity": 4, "pricelist_set_id": price_set.id}
    call(client, "GET", route(product) + "/cost", 409, params=params)
    session.add(Pricelist(pricelist_set_id=price_set.id, item_id=flour.id, price=D(80)))
    session.flush()
    call(client, "PUT", f"/api/technology/labor-rates/{production['profession_id']}/{production['qualification_id']}",
         json={"hourly_rate": 120})
    costs = call(client, "GET", route(product) + "/cost", params=params)
    assert [D(costs[key]) for key in ("material_cost", "labor_cost", "total_cost")] == [D(164), D(126), D(290)]


def test_route_rejects_cycles_invalid_units_and_removal_of_used_state(client, technology):
    catalog, production = technology
    first = catalog.item("Первое", "detail")
    second = catalog.item("Второе", "detail")
    a = operation(client, first, 10, production=production)
    z = operation(client, first, 20, production=production, output=True)
    b = operation(client, second, 10, production=production, output=True)
    bought = operation(client, second, 5)
    connect(client, first, a, z, 1, status=400)  # позднее состояние того же изделия
    connect(client, first, z, b, 1, unit=catalog.uq[("Первое", "кг")].id, status=400)
    connect(client, first, z, b, 1, status=200)
    connect(client, second, b, z, 1, status=400)  # цикл между изделиями
    connect(client, second, bought, a, 1, status=400)
    call(client, "DELETE", route(second) + f"/operations/{b}", 409)
    call(client, "GET", route(first) + "/materials", 422, params={"quantity": 0})
    call(client, "DELETE", route(first) + f"/operations/{z}/inputs/{b}", 204)
    call(client, "DELETE", route(second) + f"/operations/{b}", 204)
    call(client, "GET", route(second) + "/route", 404)


def test_import_effective_bom_is_atomic(client, technology):
    catalog, production = technology
    product = catalog.item("Пицца", "assembly", base_unit="шт")
    salt = catalog.item("Соль", "material", extra_units={"г": "0.001"})
    dough = catalog.item("Тесто", "detail")
    catalog.add("Пицца", "Соль", "12", unit="г", for_qty="2", order=1)
    catalog.add("Пицца", "Тесто", "0.3", order=2)
    op = operation(client, product, 10, production=production, output=True)
    operation(client, salt, 10, output=True)
    url = route(product) + f"/operations/{op}/import-bom"
    call(client, "POST", url, 409)
    assert call(client, "GET", route(product) + "/route")["inputs"] == []
    operation(client, dough, 10, output=True)  # в этом процессе тесто покупается
    assert len(call(client, "POST", url)) == 2
    assert len(call(client, "POST", url)) == 2
    norms = call(client, "GET", route(product) + "/materials", params={"quantity": 2})
    assert {n["item_id"]: D(n["quantity"]) for n in norms} == {salt.id: D("0.012"), dough.id: D("0.6")}


def test_template_reuse_and_rollback_of_failed_application(client, technology):
    catalog, production = technology
    product_a = catalog.item("Маленькая порция", "detail")
    product_b = catalog.item("Большая порция", "detail")
    raw_item = catalog.item("Овощи", "material")
    raw_id = operation(client, raw_item, 10, output=True)
    template = call(client, "POST", "/api/technology/templates", 201, json={
        "code": "PREP", "name": "Подготовка порции",
        "definition": {"parameters": ["size"], "steps": [
            dict(production, number=10, name="Подготовка", setup_minutes={"constant": 2}),
            dict(production, number=20, name="Фасовка", is_output=True, piece_minutes={"factors": {"size": 2}},
                 inputs=[
                     {"input_number": 10, "quantity": {"constant": 1}},
                     {"input_key": "raw", "quantity": {"factors": {"size": "0.5"}}},
                 ]),
        ]},
    })
    template_id = template["id"]
    def apply(item, size, status):
        return call(client, "POST", route(item) + f"/templates/{template_id}/apply", status,
                    json={"parameters": {"size": size}, "resources": {"raw": {"operation_id": raw_id}}})

    apply(product_a, 0, 400)
    assert call(client, "GET", route(product_a) + "/operations") == []
    assert apply(product_a, 2, 201)["template_id"] == template_id
    assert apply(product_b, 4, 201)["template_id"] == template_id
    apply(product_a, 4, 409)
    for item, quantity, minutes in [(product_a, 1, 6), (product_b, 2, 10)]:
        material, = call(client, "GET", route(item) + "/materials")
        labor, = call(client, "GET", route(item) + "/labor")
        assert D(material["quantity"]) == D(quantity)
        assert D(labor["total_minutes"]) == D(minutes)
    assert call(client, "GET", f"/api/technology/templates/{template_id}") == template
