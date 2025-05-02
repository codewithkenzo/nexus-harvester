"""Main application module for the Nexus Harvester."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.api import api_router
from nexus_harvester.mcp.server import mcp_server_manager
from nexus_harvester.utils.logging import setup_logging, get_logger, LogConfig, RequestLoggingMiddleware, bind_component

# Configure structured logging
setup_logging(LogConfig(
    ENVIRONMENT="development",  # Change to production in prod environment
    LOG_LEVEL="INFO",
    JSON_LOGS=False  # Set to True in production
))
logger = get_logger(__name__)


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
    
    # Add request logging middleware
    app.middleware("http")(RequestLoggingMiddleware())
    
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
    
    # Bind component for service startup logs
    bind_component("service")
    
    # Create app
    app = create_app()
    
    # Start MCP server
    logger.info(
        "Starting MCP server",
        component="mcp_server",
        port=settings.mcp_port,
        operation="start_server"
    )
    mcp_server_manager.start_server(settings)
    
    # Start FastAPI
    logger.info(
        "Starting API server", 
        host=settings.host,
        port=settings.port,
        component="api_server",
        operation="start_server"
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port
    )


if __name__ == "__main__":
    start_app()
