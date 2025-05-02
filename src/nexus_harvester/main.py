"""Main application module for the Nexus Harvester."""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.api import api_router
from nexus_harvester.mcp.server import mcp_server_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Nexus Harvester API",
        description="API for document ingestion and retrieval",
        version="0.1.0",
        default_response_class=ORJSONResponse
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add routes
    app.include_router(api_router)
    
    # Health check
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    return app


def start_app():
    """Start the FastAPI application with Uvicorn."""
    # Get settings
    settings = KnowledgeHarvesterSettings()
    
    # Create app
    app = create_app()
    
    # Start MCP server
    logger.info("Starting MCP server")
    mcp_server_manager.start_server(settings)
    
    # Start FastAPI
    logger.info(f"Starting FastAPI application on {settings.host}:{settings.port}")
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port
    )


if __name__ == "__main__":
    start_app()
