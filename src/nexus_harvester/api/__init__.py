"""API endpoints for the Nexus Harvester."""

from fastapi import APIRouter

from nexus_harvester.api.ingest import router as ingest_router
from nexus_harvester.api.search import router as search_router

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(ingest_router, prefix="/ingest", tags=["Ingestion"])
api_router.include_router(search_router, prefix="/search", tags=["Search"])
