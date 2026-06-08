"""Pacote de serviços de integração externa."""

from .batch import (
    extract_eans_from_file,
    extract_eans_from_text,
    lookup_batch,
    results_to_csv,
    results_to_xlsx,
    summarize,
)
from .cache import SqliteCache
from .image_search import ImageSearcher
from .ean_service import (
    APIUnavailableError,
    EANPicturesService,
    EANServiceError,
    InvalidEANError,
    ProductNotFoundError,
)

__all__ = [
    "EANPicturesService",
    "EANServiceError",
    "InvalidEANError",
    "ProductNotFoundError",
    "APIUnavailableError",
    "SqliteCache",
    "ImageSearcher",
    "extract_eans_from_file",
    "extract_eans_from_text",
    "lookup_batch",
    "results_to_csv",
    "results_to_xlsx",
    "summarize",
]
