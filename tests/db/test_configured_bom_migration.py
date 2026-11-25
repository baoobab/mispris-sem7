"""Обновление №8 сохраняет прежние строки; откат сохраняет функции в формате №7."""
from decimal import Decimal
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DATABASE_URL, alembic_config, recreate_database


def test_lab8_upgrade_and_downgrade_with_data():
    url = make_url(TEST_DATABASE_URL).set(database=make_url(TEST_DATABASE_URL).database + "_lab8_migr")
    address = url.render_as_string(hide_password=False)
    recreate_database(address)
    engine = create_engine(address)
    cfg = alembic_config(address)
    try:
        command.upgrade(cfg, "005")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO item(id,number,name) VALUES(9001,'PZ8','Пицца'),(9002,'CH8','Сыр')"))
            conn.execute(text("INSERT INTO item_bom(parent_item_id,component_item_id,quantity,for_quantity,"
                              "is_base,is_excluded,order_number,valid_from) VALUES(9001,9002,0.1,1,true,false,0,now())"))
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT quantity FROM item_bom WHERE parent_item_id=9001")).scalar_one() == Decimal("0.1")
            conn.execute(text("INSERT INTO configuration_function(id,code,name) VALUES(9001,'always8','Всегда')"))
            conn.execute(text("INSERT INTO bom_function VALUES(9001)"))
            conn.execute(text("INSERT INTO bom_conjunction VALUES(9001,1)"))
            conn.execute(text("UPDATE item_bom SET configuration_function_id=9001 WHERE parent_item_id=9001"))
            assert conn.execute(text("SELECT count(*) FROM lab8_tree(9001,'{}',now())")).scalar_one() == 1
        command.downgrade(cfg, "005")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM item_bom WHERE parent_item_id=9001")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM rule_function_definition WHERE function_id=9001")).scalar_one() == 1
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM item WHERE id IN (9001,9002)")).scalar_one() == 2
    finally:
        engine.dispose()
