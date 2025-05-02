"""Main application module for the Nexus Harvester."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from nexus_harvester.settings import KnowledgeHarvesterSettings


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
    # TODO: Import and include routers
    
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
    
    # Start FastAPI
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port
    )


if __name__ == "__main__":
    start_app()
