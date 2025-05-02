"""Dependency injection for API endpoints."""

from functools import lru_cache

from fastapi import Depends
from pydantic import SecretStr, HttpUrl

from nexus_harvester.clients.zep import ZepClient
from nexus_harvester.clients.mem0 import Mem0Client
from nexus_harvester.indexing.indexing_service import IndexingService
from nexus_harvester.settings import KnowledgeHarvesterSettings


@lru_cache
def get_settings() -> KnowledgeHarvesterSettings:
    """Get application settings."""
    return KnowledgeHarvesterSettings()


def get_zep_client(settings: KnowledgeHarvesterSettings = Depends(get_settings)) -> ZepClient:
    """Get Zep client."""
    return ZepClient(
        api_url=settings.zep_api_url,
        api_key=settings.zep_api_key
    )


def get_mem0_client(settings: KnowledgeHarvesterSettings = Depends(get_settings)) -> Mem0Client:
    """Get Mem0 client."""
    return Mem0Client(
        api_url=settings.mem0_api_url,
        api_key=settings.mem0_api_key
    )


def get_qdrant_client(settings: KnowledgeHarvesterSettings = Depends(get_settings)):
    """Get Qdrant client for development."""
    if not settings.use_qdrant_dev or not settings.qdrant_url:
        return None
    
    # Implementation for Qdrant client
    return None  # Replace with actual implementation if needed


def get_indexing_service(
    zep_client: ZepClient = Depends(get_zep_client),
    mem0_client: Mem0Client = Depends(get_mem0_client),
    qdrant_client = Depends(get_qdrant_client),
    settings: KnowledgeHarvesterSettings = Depends(get_settings)
) -> IndexingService:
    """Get indexing service."""
    return IndexingService(
        zep_client=zep_client,
        mem0_client=mem0_client,
        qdrant_client=qdrant_client,
        use_qdrant_dev=settings.use_qdrant_dev
    )
