"""MCP server for the Nexus Harvester."""

import logging
import threading
from typing import Optional

from fastmcp import MCPServer

from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.mcp.tools import (
    ingest_document_tool,
    search_knowledge_tool,
    get_memory_tool
)

# Set up logging
logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manager for the MCP server."""
    
    def __init__(self):
        """Initialize the MCP server manager."""
        self.server: Optional[MCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
    
    def create_server(self, settings: KnowledgeHarvesterSettings) -> MCPServer:
        """Create and configure the MCP server."""
        # Create MCP server
        server = MCPServer(
            name="knowledge-harvester",
            description="Knowledge harvesting and retrieval service",
            version="1.0.0"
        )
        
        # Add tools
        server.add_tool(ingest_document_tool)
        server.add_tool(search_knowledge_tool)
        server.add_tool(get_memory_tool)
        
        return server
    
    def start_server(self, settings: KnowledgeHarvesterSettings) -> None:
        """Start the MCP server in a separate thread."""
        if self.server:
            logger.warning("MCP server already running")
            return
        
        # Create server
        self.server = self.create_server(settings)
        
        # Start server in a separate thread
        self.server_thread = threading.Thread(
            target=self.server.serve_http,
            kwargs={
                "host": settings.host,
                "port": settings.mcp_port
            },
            daemon=True
        )
        self.server_thread.start()
        
        logger.info(f"MCP server started on {settings.host}:{settings.mcp_port}")
    
    def stop_server(self) -> None:
        """Stop the MCP server."""
        if not self.server:
            logger.warning("No MCP server running")
            return
        
        # Stop server
        self.server.stop()
        self.server = None
        self.server_thread = None
        
        logger.info("MCP server stopped")


# Create singleton instance
mcp_server_manager = MCPServerManager()
