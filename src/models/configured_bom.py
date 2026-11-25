"""Расширение существующих функций: реляционное тело ДНФ для строк BOM.

Отдельное тело нужно для ссылок на parameter/enum_value и групп И/ИЛИ;
заголовок функции и операторы переиспользуются из задания №7.
"""
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class BomFunction(SQLModel, table=True):
    __tablename__: ClassVar[str] = "bom_function"
    function_id: int = Field(primary_key=True, foreign_key="configuration_function.id")


class BomConjunction(SQLModel, table=True):
    __tablename__: ClassVar[str] = "bom_conjunction"
    __table_args__ = (CheckConstraint("number > 0", name="ck_bom_conjunction_number"),)
    function_id: int = Field(primary_key=True, foreign_key="bom_function.function_id")
    number: int = Field(primary_key=True)


class BomPredicate(SQLModel, table=True):
    __tablename__: ClassVar[str] = "bom_predicate"
    __table_args__ = (
        ForeignKeyConstraint(["function_id", "conjunction_number"],
                             ["bom_conjunction.function_id", "bom_conjunction.number"]),
        CheckConstraint("number > 0", name="ck_bom_predicate_number"),
        CheckConstraint("num_nonnulls(value_number, value_text, enum_value_id) = 1",
                        name="ck_bom_predicate_value"),
    )
    function_id: int = Field(primary_key=True)
    conjunction_number: int = Field(primary_key=True)
    number: int = Field(primary_key=True)
    parameter_id: int = Field(foreign_key="parameter.id")
    operator_id: int = Field(foreign_key="rule_operator.id")
    value_number: Decimal | None = Field(default=None, max_digits=18, decimal_places=6)
    value_text: str | None = Field(default=None, max_length=500)
    enum_value_id: int | None = Field(default=None, foreign_key="enum_value.id")
