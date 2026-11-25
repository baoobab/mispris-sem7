"""№8: условный состав блюд, альтернативные нормы и рекурсивный расход."""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from src.models.bom import ItemBom
from src.models.configuration import ConfigurationFunction
from src.models.enums import EnumType, EnumValue
from src.models.parameters import Parameter
from tests.e2e.test_lab7_scenarios import configurator  # noqa: F401
from tests.helpers import Catalog

ROOT = "/api/configured-bom"


def function(client, code, groups):
    response = client.post(ROOT + "/functions", json={"code": code, "name": code, "conjunctions": groups})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def numeric(parameter_id, value, operator="eq"):
    return {"parameter_id": parameter_id, "operator": operator, "value_number": value}


def position(client, item_id, component_id, qty, function_id=None, **kwargs):
    response = client.post(f"{ROOT}/items/{item_id}/positions", json={
        "component_item_id": component_id, "quantity": qty, "function_id": function_id, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, item_id, diameter, quantity=1):
    response = client.post(f"{ROOT}/items/{item_id}/preview", json={
        "values": {"diameter": diameter}, "quantity": quantity})
    assert response.status_code == 200, response.text
    return response.json()


def test_nested_food_bom_rules_alternatives_and_saved_variant(client, session, configurator):
    template = configurator
    parameter = session.exec(select(Parameter).where(Parameter.code == "diameter")).one()
    large = function(client, "large", [[numeric(parameter.id, 35, "ge")]])
    small = function(client, "small", [[numeric(parameter.id, 35, "lt")]])
    c = Catalog(session, _n=100)
    c.item("Соус", "detail")
    c.item("Томаты", "material")
    c.item("Моцарелла", "material", extra_units={"г": "0.001"})
    c.item("Пармезан", "material")
    c.add("Соус", "Томаты", "2", for_qty="4")
    position(client, template.id, c.id("Соус"), "0.2")
    position(client, template.id, c.id("Томаты"), "0.03")
    position(client, c.id("Соус"), c.id("Пармезан"), "0.1", large)
    # Один компонент, две нормы: ровно одна альтернативная строка проходит условие.
    position(client, template.id, c.id("Моцарелла"), 100, small,
             unit_quantity_id=c.uq[("Моцарелла", "г")].id)
    position(client, template.id, c.id("Моцарелла"), 200, large,
             unit_quantity_id=c.uq[("Моцарелла", "г")].id)
    for diameter, cheese in [(30, ".2"), (36, ".4")]:
        result = preview(client, template.id, diameter, quantity=2)
        norms = {r["component_item_id"]: Decimal(r["total_quantity"]) for r in result["norms"]}
        assert norms[c.id("Моцарелла")] == Decimal(cheese)
        assert norms[c.id("Томаты")] == Decimal(".26")  # две ветви + for_quantity
        assert (c.id("Пармезан") in norms) == (diameter == 36)
        assert len([r for r in result["nodes"] if r["component_item_id"] == c.id("Моцарелла")]) == 1
    saved = client.post(f"/api/configuration/items/{template.id}/variants", json={
        "number": "PZ-LAB8", "name": "Большая пицца", "values": {"diameter": 36}})
    assert saved.status_code == 201, saved.text
    variant_id = saved.json()["item"]["id"]
    actual = client.get(f"{ROOT}/items/{variant_id}/specification?quantity=2")
    assert actual.status_code == 200, actual.text
    assert actual.json()["norms"] == preview(client, template.id, 36, 2)["norms"]
    # Встроенные функции №7 продолжают работать при наличии реляционных функций №8.
    assert client.get("/api/configuration/functions").status_code == 200


def test_or_and_empty_forms_and_crud(client, session, configurator):
    p = session.exec(select(Parameter).where(Parameter.code == "diameter")).one()
    f = function(client, "orAnd", [[numeric(p.id, 25), numeric(p.id, 20, "gt")], [numeric(p.id, 35)]])
    from src.repository.configured_bom_repository import ConfiguredBomRepository
    repo = ConfiguredBomRepository(session)
    assert [repo.evaluate(f, {p.id: Decimal(v)}) for v in (25, 30, 35)] == [True, False, True]
    assert repo.evaluate(function(client, "never", []), {}) is False
    assert repo.evaluate(function(client, "always", [[]]), {}) is True
    assert client.put(f"{ROOT}/functions/{f}", json={"code": "orAnd", "name": "Изменено",
                      "conjunctions": []}).status_code == 200
    assert repo.evaluate(f, {p.id: 25}) is False
    assert len(client.get(ROOT + "/functions").json()) == 3
    assert client.delete(f"{ROOT}/functions/{f}").status_code == 204
    assert client.get(f"{ROOT}/functions/{f}").status_code == 404


def test_condition_versions_detach_and_norm_edit_preserve_rule(client, session, configurator):
    p = session.exec(select(Parameter).where(Parameter.code == "diameter")).one()
    f = function(client, "onlyLarge", [[numeric(p.id, 35, "ge")]])
    c = Catalog(session, _n=100)
    c.item("Сыр", "material")
    original = position(client, configurator.id, c.id("Сыр"), ".1")
    endpoint = f"{ROOT}/items/{configurator.id}/components/{c.id('Сыр')}/condition"
    response = client.put(endpoint, json={"function_id": f})
    assert response.status_code == 200, response.text
    assert session.get(ItemBom, original["id"]).valid_to is not None
    assert preview(client, configurator.id, 30)["nodes"] == []
    assert len(preview(client, configurator.id, 36)["nodes"]) == 1
    changed = client.put(f"/api/items/{configurator.id}/bom/{c.id('Сыр')}", json={"quantity": ".2"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["configuration_function_id"] == f
    assert client.delete(f"{ROOT}/functions/{f}").status_code == 409
    assert client.put(endpoint, json={"function_id": None}).status_code == 200
    assert Decimal(preview(client, configurator.id, 30)["norms"][0]["total_quantity"]) == Decimal(".2")
    history = client.get(f"/api/items/{configurator.id}/bom/changes").json()
    assert len(history) == 4


def test_invalid_parameters_missing_function_and_atomic_position_edit(client, session, configurator):
    p = session.exec(select(Parameter).where(Parameter.code == "diameter")).one()
    payload = {"code": "bad", "name": "bad", "conjunctions": [[{"parameter_id": p.id, "value_text": "x"}]]}
    assert client.post(ROOT + "/functions", json=payload).status_code == 400
    assert not session.exec(select(ConfigurationFunction).where(ConfigurationFunction.code == "bad")).all()
    assert client.post(f"{ROOT}/items/{configurator.id}/preview", json={}).status_code == 400
    assert client.post(f"{ROOT}/items/{configurator.id}/preview", json={"values": {"diameter": 100}}).status_code == 400
    c = Catalog(session, _n=100)
    c.item("Сыр", "material")
    row = position(client, configurator.id, c.id("Сыр"), ".1")
    endpoint = f"{ROOT}/items/{configurator.id}/positions/{row['id']}"
    assert client.put(endpoint, json={"component_item_id": c.id("Сыр"), "quantity": ".2",
                                     "function_id": 999999}).status_code == 404
    assert session.get(ItemBom, row["id"]).valid_to is None
    assert client.delete(endpoint).status_code == 204
    assert preview(client, configurator.id, 30)["nodes"] == []


def test_enum_predicate_uses_existing_dictionary_and_rejects_other_enum(client, session):
    enums = [EnumType(code=code, name=code) for code in ("param_type", "board", "foreign")]
    session.add_all(enums)
    session.flush()
    typ, board, wrong = [EnumValue(enum_type_id=e.id, code=code, name=code, order_number=1)
                         for e, code in zip(enums, ("enum", "cheese", "wrong"))]
    session.add_all([typ, board, wrong]); session.flush()
    p = Parameter(code="board", name="Борт", param_type_id=typ.id, enum_type_id=enums[1].id)
    session.add(p); session.flush()
    bad = {"code": "enumBad", "name": "Ошибка", "conjunctions": [[{
        "parameter_id": p.id, "enum_value_id": wrong.id}]]}
    assert client.post(ROOT + "/functions", json=bad).status_code == 400
    f = function(client, "cheese", [[{"parameter_id": p.id, "enum_value_id": board.id}]])
    from src.repository.configured_bom_repository import ConfiguredBomRepository
    assert ConfiguredBomRepository(session).evaluate(f, {p.id: board.id}) is True
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.delete(board)
            session.flush()  # настоящий FK на enum_value, а не строка в условии


def test_cycle_is_rejected_and_transaction_rolled_back(client, session):
    c = Catalog(session, _n=100)
    c.item("Пицца", "assembly")
    c.item("Набор", "complex")
    position(client, c.id("Набор"), c.id("Пицца"), 2)
    response = client.post(f"{ROOT}/items/{c.id('Пицца')}/positions", json={
        "component_item_id": c.id("Набор"), "quantity": 1})
    assert response.status_code == 400, response.text
    assert not session.exec(select(ItemBom).where(ItemBom.parent_item_id == c.id("Пицца"))).all()
    # Защита хранимой функции и при обходе API.
    session.execute(text("INSERT INTO item_bom(parent_item_id,component_item_id,quantity,for_quantity,"
                         "is_base,is_excluded,order_number,valid_from) VALUES(:p,:c,1,1,true,false,0,now())"),
                    {"p": c.id("Пицца"), "c": c.id("Набор")})
    response = client.get(f"{ROOT}/items/{c.id('Набор')}/specification")
    assert response.status_code == 400, response.text


def test_excluded_subassembly_does_not_expand_and_empty_assembly_is_not_material(client, session, configurator):
    c = Catalog(session, _n=100)
    c.item("Соус", "detail")
    c.item("Томаты", "material")
    never = function(client, "never", [])
    edge = position(client, configurator.id, c.id("Соус"), 1, never)
    position(client, c.id("Соус"), c.id("Томаты"), 2)
    assert preview(client, configurator.id, 30)["nodes"] == []
    assert client.put(f"{ROOT}/items/{configurator.id}/positions/{edge['id']}", json={
        "component_item_id": c.id("Соус"), "quantity": 1}).status_code == 200
    endpoint = f"{ROOT}/items/{c.id('Соус')}/components/{c.id('Томаты')}/condition"
    assert client.put(endpoint, json={"function_id": never}).status_code == 200
    result = preview(client, configurator.id, 30)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["is_leaf"] is False
    assert result["norms"] == []


def test_modification_inherits_conditions_and_historical_bom(client, session, configurator):
    c = Catalog(session, _n=100)
    c.item("Сыр", "material")
    row = position(client, configurator.id, c.id("Сыр"), ".1")
    old_at = session.get(ItemBom, row["id"]).valid_from.isoformat()
    f = function(client, "disabled", [])
    endpoint = f"{ROOT}/items/{configurator.id}/components/{c.id('Сыр')}/condition"
    assert client.put(endpoint, json={"function_id": f}).status_code == 200
    old = client.post(f"{ROOT}/items/{configurator.id}/preview", json={
        "values": {"diameter": 30}, "at": old_at})
    assert old.status_code == 200, old.text
    assert len(old.json()["nodes"]) == 1
    # Простое изделие-модификация без параметров: унаследованное FALSE вычисляется в БД.
    modified = client.post(f"/api/items/{configurator.id}/modifications", json={"name": "Модификация"})
    assert modified.status_code == 201, modified.text
    result = client.get(f"{ROOT}/items/{modified.json()['id']}/specification")
    assert result.status_code == 200, result.text
    assert result.json()["norms"] == []

