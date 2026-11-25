from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.config.config import settings
from src.core.errors import DomainError
from src.routers.summaries import apply_summaries
from src.routers import (
    bom,
    classifiers,
    documents,
    enums,
    ho,
    items,
    packaging,
    parameters,
    positions,
    roles,
    sxd,
    technology,
    units,
)

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "API информационной системы сервиса доставки готовой еды: классификаторы, перечисления, "
        "параметры, справочник изделий, хозяйственные операции (№4) и материальные спецификации "
        "изделий — BOM, модификации, история изменений, сводные нормы расхода (№5). "
        "Маршрутная технология, типовые процессы, нормы расхода, трудоёмкость и себестоимость (№6). "
        "Конфигурируемые изделия, варианты исполнения, сложные ограничения и заказы (№7). "
        "Условные позиции BOM, функции ДНФ, состав варианта и сводные нормы расхода (№8)."
    ),
)


@app.exception_handler(DomainError)
def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(IntegrityError)
def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Нарушение ограничений БД (уникальность, FK, CHECK) — конфликт с текущими данными
    message = str(exc.orig).splitlines()[0] if exc.orig is not None else str(exc)
    return JSONResponse(status_code=409, content={"detail": f"Нарушено ограничение целостности БД: {message}"})


app.include_router(enums.router, prefix="/api/enums", tags=["Перечисления"])
app.include_router(units.router, prefix="/api/units", tags=["Единицы измерения"])
app.include_router(parameters.router, prefix="/api/parameters", tags=["Параметры"])
app.include_router(classifiers.router, prefix="/api/classifiers", tags=["Классификаторы"])
app.include_router(roles.router, prefix="/api/roles", tags=["Роли"])
app.include_router(sxd.router, prefix="/api/sxd", tags=["СХД"])
app.include_router(ho.router, prefix="/api/ho", tags=["Хозяйственные операции"])
app.include_router(documents.router, prefix="/api/documents", tags=["Документы"])
app.include_router(items.router, prefix="/api/items", tags=["Номенклатура"])
app.include_router(bom.router, prefix="/api/items", tags=["Спецификации изделий (BOM)"])
app.include_router(packaging.router, prefix="/api/packaging", tags=["Упаковка"])
app.include_router(positions.router, prefix="/api/positions", tags=["Позиции и прейскуранты"])
app.include_router(technology.catalog_router, prefix="/api/technology", tags=["Справочники технологии"])
app.include_router(
    technology.route_router, prefix="/api/items/{item_id}/technology", tags=["Маршрутная технология"],
)


@app.get("/health", tags=["Служебное"])
def health():
    return {"status": "ok"}


apply_summaries(app)

# Операции №7 содержат русские summary непосредственно в декораторах.
from src.routers.configuration import router as configuration_router
app.include_router(configuration_router, prefix="/api/configuration", tags=["Конфигурации и заказы (№7)"])

from src.routers.configured_bom import router as configured_bom_router
app.include_router(configured_bom_router, prefix="/api/configured-bom", tags=["Спецификации с вариантами (№8)"])


@app.get("/openapi-lab7.json", include_in_schema=False)
def lab7_openapi():
    from copy import deepcopy
    schema = deepcopy(app.openapi())
    schema["paths"] = {path: operations for path, operations in schema["paths"].items()
                       if path.startswith("/api/configuration")}
    schema["info"]["title"] = "МиСПрИС — заказы с вариантами исполнения (№7)"
    return schema


@app.get("/docs/lab7", include_in_schema=False)
def lab7_docs():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/openapi-lab7.json", title="МиСПрИС №7 — Swagger",
                               swagger_ui_parameters={"defaultModelsExpandDepth": -1})
