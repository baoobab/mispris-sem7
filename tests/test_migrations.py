"""Миграции Alembic: чистая БД -> head -> base -> head, схема совпадает с моделями."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

import src.models  # noqa: F401  — регистрация всех таблиц в metadata
from tests.conftest import TEST_DATABASE_URL, alembic_config, recreate_database

MIGR_URL = make_url(TEST_DATABASE_URL).set(database=make_url(TEST_DATABASE_URL).database + "_migr")
MIGR_URL_STR = MIGR_URL.render_as_string(hide_password=False)


def test_upgrade_downgrade_upgrade():
    recreate_database(MIGR_URL_STR)
    cfg = alembic_config(MIGR_URL_STR)
    engine = create_engine(MIGR_URL_STR)
    try:
        command.upgrade(cfg, "002")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO item (number, name) VALUES ('LEGACY', 'Legacy item')"))
        command.upgrade(cfg, "head")
        tables = set(inspect(engine).get_table_names())
        assert {"item_bom", "item_change", "unit_simple", "technology_operation", "technology_input"} <= tables
        assert "unit_simple_id" not in tables  # таблица переименована
        with engine.connect() as connection:
            assert connection.execute(text("SELECT name FROM item WHERE number = 'LEGACY'")).scalar_one() == "Legacy item"
            assert connection.execute(text("SELECT to_regprocedure('mr_q(integer,double precision)') IS NOT NULL")).scalar_one()

        command.downgrade(cfg, "002")
        assert "technology_operation" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT to_regprocedure('find_tm(integer)') IS NULL")).scalar_one()
            assert connection.execute(text("SELECT name FROM item WHERE number = 'LEGACY'")).scalar_one() == "Legacy item"
        command.downgrade(cfg, "001")
        tables = set(inspect(engine).get_table_names())
        assert "item_bom" not in tables and "item_change" not in tables

        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        assert "item_bom" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_models_match_migrations():
    """Autogenerate не должен находить расхождений между моделями и схемой после миграций."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), SQLModel.metadata)
    finally:
        engine.dispose()
    # Индексы/ограничения, которые описаны только в миграции, сравниваем мягко: важны таблицы и колонки
    significant = [d for d in diff if d[0] in ("add_table", "remove_table", "add_column", "remove_column")]
    assert significant == []
