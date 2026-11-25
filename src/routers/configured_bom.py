from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from src.database.database import get_session
from src.repository.configured_bom_repository import ConfiguredBomRepository
from src.routers.bom import get_bom_service
from src.schemas.configured_bom import BomPreviewInput, ConditionInput, ConfiguredBomRead, FunctionInput, PositionInput
from src.services.bom_service import BomService
from src.services.configured_bom_service import ConfiguredBomService

router = APIRouter()


def get_service(session: Session = Depends(get_session)):
    return ConfiguredBomService(ConfiguredBomRepository(session))


@router.get("/functions", summary="Получить функции включения позиций BOM")
def functions(service=Depends(get_service)):
    return service.functions()


@router.post("/functions", status_code=201, summary="Создать функцию как ИЛИ групп И")
def create_function(data: FunctionInput, service=Depends(get_service)):
    return service.write_function(data)


@router.get("/functions/{function_id}", summary="Прочитать структуру функции включения")
def function(function_id: int, service=Depends(get_service)):
    return service.function(function_id)


@router.put("/functions/{function_id}", summary="Изменить функцию включения позиций")
def update_function(function_id: int, data: FunctionInput, service=Depends(get_service)):
    return service.write_function(data, function_id)


@router.delete("/functions/{function_id}", status_code=204, summary="Удалить неиспользуемую функцию")
def delete_function(function_id: int, service=Depends(get_service)):
    service.delete_function(function_id)


@router.put("/items/{item_id}/components/{component_id}/condition",
            summary="Назначить или снять условие включения компонента")
def set_condition(item_id: int, component_id: int, data: ConditionInput,
                  service=Depends(get_service), bom: BomService = Depends(get_bom_service)):
    return service.set_condition(item_id, component_id, data, bom)


@router.post("/items/{item_id}/positions", status_code=201,
             summary="Добавить позицию с условием и нормой расхода")
def add_position(item_id: int, data: PositionInput, service=Depends(get_service),
                 bom: BomService = Depends(get_bom_service)):
    return service.write_position(item_id, data, bom)


@router.put("/items/{item_id}/positions/{bom_id}", summary="Изменить позицию по идентификатору строки")
def edit_position(item_id: int, bom_id: int, data: PositionInput, service=Depends(get_service),
                  bom: BomService = Depends(get_bom_service)):
    return service.write_position(item_id, data, bom, bom_id)


@router.delete("/items/{item_id}/positions/{bom_id}", status_code=204,
               summary="Удалить позицию конфигурируемой спецификации")
def delete_position(item_id: int, bom_id: int, service=Depends(get_service),
                    bom: BomService = Depends(get_bom_service)):
    service.delete_position(item_id, bom_id, bom)


@router.post("/items/{item_id}/preview", response_model=ConfiguredBomRead,
             summary="Сформировать состав и сводные нормы по выбранным параметрам")
def preview(item_id: int, data: BomPreviewInput, service=Depends(get_service)):
    return service.build(item_id, data.quantity, data.at, data.values)


@router.get("/items/{item_id}/specification", response_model=ConfiguredBomRead,
            summary="Получить состав и нормы сохранённого варианта или простого изделия")
def specification(item_id: int, quantity: Decimal = Query(default=Decimal(1), gt=0,
                  max_digits=18, decimal_places=6), at: datetime | None = None,
                  service=Depends(get_service)):
    return service.build(item_id, quantity, at)
