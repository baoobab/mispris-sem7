# Импорт всех моделей необходим для регистрации в SQLModel.metadata (используется Alembic)
from src.models.bom import ItemBom, ItemChange
from src.models.classifiers import DocumentClassifier, HoClassifier, ItemClassifier, SxdClassifier
from src.models.enums import EnumType, EnumValue
from src.models.ho import DocClassParameter, Document, Ho, HoClassParameter, SxdRoleInHo
from src.models.items import Item, ItemBatch, UnitQuantity
from src.models.packaging import Packaging, PackagingNorm, PackagingType
from src.models.param_values import DocParameterValue, HoParameterValue
from src.models.parameters import Parameter
from src.models.positions import HoPosition, Pricelist, PricelistSet, PositionList
from src.models.roles import AvailableRoles, SxdRole
from src.models.sxd import Sxd
from src.models.technology import (
    TechnologyApplication,
    TechnologyAsset,
    TechnologyAssetModel,
    TechnologyClass,
    TechnologyInput,
    TechnologyLaborRate,
    TechnologyOperation,
    TechnologyTemplate,
    TechnologyToolRequirement,
    WorkCenter,
)
from src.models.units import UnitSimple

__all__ = [
    "EnumType",
    "EnumValue",
    "UnitSimple",
    "Parameter",
    "SxdClassifier",
    "HoClassifier",
    "DocumentClassifier",
    "ItemClassifier",
    "SxdRole",
    "AvailableRoles",
    "HoClassParameter",
    "DocClassParameter",
    "Sxd",
    "Ho",
    "Document",
    "HoParameterValue",
    "DocParameterValue",
    "SxdRoleInHo",
    "Item",
    "UnitQuantity",
    "ItemBatch",
    "PackagingType",
    "Packaging",
    "PackagingNorm",
    "PricelistSet",
    "Pricelist",
    "PositionList",
    "HoPosition",
    "ItemBom",
    "ItemChange",
    "TechnologyApplication",
    "TechnologyAsset",
    "TechnologyAssetModel",
    "TechnologyClass",
    "TechnologyInput",
    "TechnologyLaborRate",
    "TechnologyOperation",
    "TechnologyTemplate",
    "TechnologyToolRequirement",
    "WorkCenter",
]
