from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from src.database.database import get_session
from src.models import (
    TechnologyApplication, TechnologyAsset, TechnologyAssetModel, TechnologyClass, TechnologyLaborRate,
    TechnologyTemplate, WorkCenter,
)
from src.repository.technology_repository import TechnologyRepository
from src.schemas.technology import (
    ApplicationRead, AssetCreate, AssetModelCreate, AssetModelRead, AssetRead, ClassCreate, ClassKind, ClassRead,
    CostRead, Id, InputNorm, InputRead, LaborNorm, LaborRate, LaborRateRead, MaterialNorm, OperationCreate,
    OperationMaterialNorm, OperationRead, OperationWithResources, RouteRead, TemplateApply, TemplateCreate,
    TemplateRead, ToolQuantity, ToolRead, WorkCenterCreate, WorkCenterRead,
)
from src.services.technology_service import TechnologyService

catalog_router = APIRouter()
route_router = APIRouter()
Quantity = Annotated[Decimal, Query(gt=0, max_digits=24, decimal_places=9, description="Количество в базовой ЕИ")]
Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]


def get_service(session: Session = Depends(get_session)) -> TechnologyService:
    return TechnologyService(TechnologyRepository(session))


Service = Annotated[TechnologyService, Depends(get_service)]


@catalog_router.get("/classes", response_model=list[ClassRead])
def list_classes(service: Service, kind: ClassKind | None = None, skip: Skip = 0, limit: Limit = 100):
    where = () if kind is None else (TechnologyClass.kind == kind,)
    return service.repo.list_catalog(TechnologyClass, where=where, skip=skip, limit=limit)


@catalog_router.post("/classes", response_model=ClassRead, status_code=201)
def create_class(data: ClassCreate, service: Service):
    return service.save_class(data)


@catalog_router.put("/classes/{class_id}", response_model=ClassRead)
def update_class(class_id: Id, data: ClassCreate, service: Service):
    return service.save_class(data, class_id)


@catalog_router.get("/work-centers", response_model=list[WorkCenterRead])
def list_work_centers(service: Service, skip: Skip = 0, limit: Limit = 100):
    return service.repo.list_catalog(WorkCenter, skip=skip, limit=limit)


@catalog_router.post("/work-centers", response_model=WorkCenterRead, status_code=201)
def create_work_center(data: WorkCenterCreate, service: Service):
    return service.save_work_center(data)


@catalog_router.put("/work-centers/{center_id}", response_model=WorkCenterRead)
def update_work_center(center_id: Id, data: WorkCenterCreate, service: Service):
    return service.save_work_center(data, center_id)


@catalog_router.get("/asset-models", response_model=list[AssetModelRead])
def list_asset_models(service: Service, skip: Skip = 0, limit: Limit = 100):
    return service.repo.list_catalog(TechnologyAssetModel, skip=skip, limit=limit)


@catalog_router.post("/asset-models", response_model=AssetModelRead, status_code=201)
def create_asset_model(data: AssetModelCreate, service: Service):
    return service.repo.save(TechnologyAssetModel(**data.model_dump()))


@catalog_router.get("/assets", response_model=list[AssetRead])
def list_assets(service: Service, work_center_id: Id | None = None, skip: Skip = 0, limit: Limit = 100):
    where = () if work_center_id is None else (TechnologyAsset.work_center_id == work_center_id,)
    return service.repo.list_catalog(TechnologyAsset, where=where, skip=skip, limit=limit)


@catalog_router.post("/assets", response_model=AssetRead, status_code=201)
def create_asset(data: AssetCreate, service: Service):
    return service.save_asset(data)


@catalog_router.put("/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: Id, data: AssetCreate, service: Service):
    return service.save_asset(data, asset_id)


@catalog_router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: Id, service: Service):
    service.repo.delete(service.require(TechnologyAsset, asset_id, "Инвентарная единица"))


@catalog_router.get("/labor-rates/{profession_id}/{qualification_id}", response_model=LaborRateRead)
def get_rate(profession_id: Id, qualification_id: Id, service: Service):
    return service.require(TechnologyLaborRate, (profession_id, qualification_id), "Часовая ставка")


@catalog_router.put("/labor-rates/{profession_id}/{qualification_id}", response_model=LaborRateRead)
def put_rate(profession_id: Id, qualification_id: Id, data: LaborRate, service: Service):
    return service.put_rate(profession_id, qualification_id, data.hourly_rate)


@catalog_router.get("/templates", response_model=list[TemplateRead])
def list_templates(service: Service, skip: Skip = 0, limit: Limit = 100):
    return service.repo.list_catalog(TechnologyTemplate, skip=skip, limit=limit)


@catalog_router.post("/templates", response_model=TemplateRead, status_code=201)
def create_template(data: TemplateCreate, service: Service):
    return service.create_template(data)


@catalog_router.get("/templates/{template_id}", response_model=TemplateRead)
def get_template(template_id: Id, service: Service):
    return service.require(TechnologyTemplate, template_id, "Типовой процесс")


@route_router.get("/operations", response_model=list[OperationRead])
def list_operations(item_id: Id, service: Service):
    return service.list_operations(item_id)


@route_router.post("/operations", response_model=OperationRead, status_code=201)
def create_operation(item_id: Id, data: OperationCreate, service: Service):
    return service.save_operation(item_id, data)


@route_router.get("/operations/{operation_id}", response_model=OperationWithResources)
def get_operation(item_id: Id, operation_id: Id, service: Service):
    return service.get_operation(item_id, operation_id)


@route_router.put("/operations/{operation_id}", response_model=OperationRead)
def update_operation(item_id: Id, operation_id: Id, data: OperationCreate, service: Service):
    return service.save_operation(item_id, data, operation_id)


@route_router.delete("/operations/{operation_id}", status_code=204)
def delete_operation(item_id: Id, operation_id: Id, service: Service):
    service.delete_operation(item_id, operation_id)


@route_router.put("/operations/{operation_id}/inputs/{input_id}", response_model=InputRead)
def put_input(item_id: Id, operation_id: Id, input_id: Id, data: InputNorm, service: Service):
    return service.put_input(item_id, operation_id, input_id, data)


@route_router.delete("/operations/{operation_id}/inputs/{input_id}", status_code=204)
def delete_input(item_id: Id, operation_id: Id, input_id: Id, service: Service):
    service.delete_input(item_id, operation_id, input_id)


@route_router.post("/operations/{operation_id}/import-bom", response_model=list[InputRead])
def import_bom(item_id: Id, operation_id: Id, service: Service, at: datetime | None = None):
    return service.import_bom(item_id, operation_id, at)


@route_router.put("/operations/{operation_id}/tools/{model_id}", response_model=ToolRead)
def put_tool(item_id: Id, operation_id: Id, model_id: Id, data: ToolQuantity, service: Service):
    return service.put_tool(item_id, operation_id, model_id, data.quantity)


@route_router.delete("/operations/{operation_id}/tools/{model_id}", status_code=204)
def delete_tool(item_id: Id, operation_id: Id, model_id: Id, service: Service):
    service.delete_tool(item_id, operation_id, model_id)


@route_router.get("/route", response_model=RouteRead)
def find_route(item_id: Id, service: Service):
    return service.find_route(item_id)


@route_router.get("/operations/{operation_id}/materials", response_model=list[OperationMaterialNorm])
def operation_materials(item_id: Id, operation_id: Id, service: Service, quantity: Quantity = Decimal(1)):
    return service.direct_materials(item_id, operation_id, quantity)


@route_router.get("/materials", response_model=list[MaterialNorm])
def materials(item_id: Id, service: Service, quantity: Quantity = Decimal(1)):
    return service.materials(item_id, quantity)


@route_router.get("/labor", response_model=list[LaborNorm])
def labor(item_id: Id, service: Service, quantity: Quantity = Decimal(1)):
    return service.labor(item_id, quantity)


@route_router.get("/cost", response_model=CostRead)
def cost(item_id: Id, pricelist_set_id: Annotated[int, Query(gt=0, le=2_147_483_647)],
         service: Service, quantity: Quantity = Decimal(1)):
    return service.cost(item_id, quantity, pricelist_set_id)


@route_router.post("/templates/{template_id}/apply", response_model=ApplicationRead, status_code=201)
def apply_template(item_id: Id, template_id: Id, data: TemplateApply, service: Service):
    return service.apply_template(item_id, template_id, data)


@route_router.get("/template-application", response_model=ApplicationRead)
def get_application(item_id: Id, service: Service):
    return service.require(TechnologyApplication, item_id, "Применение типового процесса")
