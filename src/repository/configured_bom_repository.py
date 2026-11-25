import json
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.core.errors import BusinessRuleError
from src.repository.configuration_repository import ConfigurationRepository


def values_json(values):
    """Числа Decimal передаются JSON-числами без потери точности через float."""
    return "{" + ",".join(json.dumps(str(k)) + ":" + (
        str(v) if isinstance(v, Decimal) else json.dumps(v, ensure_ascii=False)
    ) for k, v in values.items()) + "}"


class ConfiguredBomRepository(ConfigurationRepository):
    def execute_function(self, sql, parameters):
        try:
            return self.session.execute(text(sql), parameters)
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) == "P0001":
                raise BusinessRuleError(str(exc.orig).splitlines()[0]) from exc
            raise

    def evaluate(self, function_id, values):
        return self.execute_function(
            "SELECT lab8_eval(:id,CAST(:values AS jsonb))",
            {"id": function_id, "values": values_json(values)},
        ).scalar_one()

    def tree(self, item_id, values, at):
        return self.execute_function(
            "SELECT * FROM lab8_tree(:item,CAST(:values AS jsonb),:at)",
            {"item": item_id, "values": values_json(values), "at": at},
        ).mappings().all()

    def norms(self, item_id, values, at, quantity):
        return self.execute_function(
            "SELECT * FROM lab8_norms(:item,CAST(:values AS jsonb),:at,:quantity)",
            {"item": item_id, "values": values_json(values), "at": at, "quantity": quantity},
        ).mappings().all()
