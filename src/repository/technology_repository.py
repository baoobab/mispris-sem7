from decimal import Decimal
from typing import TypeVar

from sqlalchemy import func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import SQLModel, Session, col, select

from src.models.technology import (
    TechnologyInput,
    TechnologyLaborRate,
    TechnologyOperation,
    TechnologyToolRequirement,
)

Model = TypeVar("Model", bound=SQLModel)


class TechnologyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, model: type[Model], key) -> Model | None:
        return self.session.get(model, key)

    def list_catalog(self, model, *, skip=0, limit=100, where=()):
        return self.session.exec(select(model).where(*where).order_by(model.id).offset(skip).limit(limit)).all()

    def save(self, row: Model) -> Model:
        self.session.add(row)
        self.session.flush()
        return row

    def delete(self, row: SQLModel):
        self.session.delete(row)
        self.session.flush()

    def lock_graph(self, *, shared=False):
        # Изменения разных изделий могут замкнуть общий цикл. Один замок на граф
        # сериализует проверку и запись, в том числе при применении шаблона.
        lock = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        self.session.execute(text(f"SELECT {lock}(6006, 1)"))

    def operations(self, item_id: int):
        return self.session.exec(
            select(TechnologyOperation).where(TechnologyOperation.item_id == item_id)
            .order_by(TechnologyOperation.number)
        ).all()

    def output(self, item_id: int):
        return self.session.exec(select(TechnologyOperation).where(
            TechnologyOperation.item_id == item_id, col(TechnologyOperation.is_output).is_(True),
        )).first()

    def linked_operations(self, operation_id: int):
        """Соседи для проверки смены номера или превращения в закупку."""
        return self.session.exec(
            select(TechnologyInput, TechnologyOperation)
            .join(TechnologyOperation, or_(
                (TechnologyInput.out_operation_id == operation_id)
                & (TechnologyOperation.id == TechnologyInput.in_operation_id),
                (TechnologyInput.in_operation_id == operation_id)
                & (TechnologyOperation.id == TechnologyInput.out_operation_id),
            ))
        ).all()

    def creates_cycle(self, out_id: int, in_id: int) -> bool:
        return self.session.execute(text("""
            WITH RECURSIVE reachable(id) AS (
                SELECT CAST(:in_id AS integer)
                UNION
                SELECT e.in_operation_id FROM reachable r
                JOIN technology_input e ON e.out_operation_id = r.id
            )
            SELECT EXISTS (SELECT 1 FROM reachable WHERE id = :out_id)
        """), {"in_id": in_id, "out_id": out_id}).scalar_one()

    def route_operations(self, item_id: int):
        route = func.find_tm(item_id).table_valued("operation_id", "depth")
        return self.session.exec(
            select(TechnologyOperation, route.c.depth).select_from(TechnologyOperation)
            .join(route, route.c.operation_id == TechnologyOperation.id)
            .order_by(route.c.depth, TechnologyOperation.item_id, TechnologyOperation.number)
        ).all()

    def inputs(self, operation_ids: list[int]):
        return self.session.exec(select(TechnologyInput).where(
            col(TechnologyInput.out_operation_id).in_(operation_ids),
        ).order_by(TechnologyInput.out_operation_id, TechnologyInput.in_operation_id)).all()

    def tools(self, operation_ids: list[int]):
        return self.session.exec(select(TechnologyToolRequirement).where(
            col(TechnologyToolRequirement.operation_id).in_(operation_ids),
        ).order_by(TechnologyToolRequirement.operation_id, TechnologyToolRequirement.model_id)).all()

    def direct_materials(self, operation_id: int, quantity: Decimal):
        return self.session.execute(text(
            "SELECT * FROM mr_q(:id, CAST(:quantity AS numeric)) ORDER BY in_operation_id"
        ), {"id": operation_id, "quantity": quantity}).mappings().all()

    def materials(self, item_id: int, quantity: Decimal, price_set_id: int | None = None):
        if price_set_id is None:
            query = "SELECT m.* FROM sum_mr(:id, CAST(:quantity AS numeric)) m"
        else:
            query = """
                SELECT m.*, p.price FROM sum_mr(:id, CAST(:quantity AS numeric)) m
                LEFT JOIN pricelist p ON p.item_id = m.item_id AND p.pricelist_set_id = :price_set_id
            """
        return self.session.execute(
            text(query + " ORDER BY m.item_id, m.unit_quantity_id"),
            {"id": item_id, "quantity": quantity, "price_set_id": price_set_id},
        ).mappings().all()

    def labor(self, item_id: int, quantity: Decimal, with_rates=False):
        query = "SELECT l.* FROM tr_to(:id, CAST(:quantity AS numeric)) l"
        if with_rates:
            query = """
                SELECT l.*, r.hourly_rate FROM tr_to(:id, CAST(:quantity AS numeric)) l
                LEFT JOIN technology_labor_rate r USING (profession_id, qualification_id)
            """
        return self.session.execute(
            text(query + " ORDER BY l.profession_id, l.qualification_id"), {"id": item_id, "quantity": quantity},
        ).mappings().all()

    def put_rate(self, profession_id: int, qualification_id: int, hourly_rate: Decimal):
        values = dict(profession_id=profession_id, qualification_id=qualification_id, hourly_rate=hourly_rate)
        stmt = insert(TechnologyLaborRate).values(**values)
        self.session.execute(stmt.on_conflict_do_update(
            index_elements=["profession_id", "qualification_id"], set_={"hourly_rate": hourly_rate},
        ))
        return values
