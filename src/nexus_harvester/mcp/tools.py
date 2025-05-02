"""MCP tools for the Nexus Harvester."""

import logging
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4

from fastmcp import FastMCP
from pydantic import BaseModel, Field, HttpUrl

from nexus_harvester.models import DocumentMeta
from nexus_harvester.api.ingest import process_and_index_document
from nexus_harvester.api.dependencies import get_mem0_client

# Set up logging
logger = logging.getLogger(__name__)

mcp = FastMCP("Nexus Harvester") # Instantiate FastMCP

# MCP request/response models
class IngestRequest(BaseModel):
    """Request model for document ingestion."""
    url: HttpUrl
    title: str
    source: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    """Response model for document ingestion."""
    doc_id: str
    job_id: str
    status: str


class SearchRequest(BaseModel):
    """Request model for document search."""
    query: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResponse(BaseModel):
    """Response model for document search."""
    results: List[Dict[str, Any]]
    query: str
    count: int


# Define MCP tools
@mcp.tool(name="ingest_document", description="Ingest a document for processing")
async def ingest_document_tool(request: IngestRequest) -> IngestResponse:
    """Ingest a document via MCP."""
    logger.info(f"MCP tool called: ingest_document for {request.title}")
    
    # Convert to DocumentMeta
    doc_meta = DocumentMeta(
        url=request.url,
        title=request.title,
        source=request.source,
        metadata=request.metadata
    )
    
    # Process document
    job_id = str(uuid4())
    
    # Start processing in background
    process_and_index_document(
        job_id=job_id,
        doc_meta=doc_meta,
        content=request.content
    )
    
    return IngestResponse(
        doc_id=str(doc_meta.id),
        job_id=job_id,
        status="accepted"
    )


@mcp.tool(name="search_knowledge", description="Search indexed documents")
async def search_knowledge_tool(request: SearchRequest) -> SearchResponse:
    """Search documents via MCP."""
    logger.info(f"MCP tool called: search_knowledge for query '{request.query}'")
    
    try:
        # Get Mem0 client
        mem0_client = get_mem0_client()
        
        # Execute search
        results = await mem0_client.search(
            query=request.query,
            filters=request.filters,
            limit=request.limit
        )
        
        return SearchResponse(
            results=results,
            query=request.query,
            count=len(results)
        )
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise


@mcp.tool(name="get_memory", description="Retrieve memory context")
async def get_memory_tool(session_id: str, limit: int = 10) -> Dict[str, Any]:
    """Retrieve memory context via MCP."""
    logger.info(f"MCP tool called: get_memory for session '{session_id}'")
    
    try:
        # Get Zep client
        from nexus_harvester.api.dependencies import get_zep_client
        zep_client = get_zep_client()
        
        # Retrieve memory
        memory = await zep_client.get_memory(session_id, limit)
        
        return {
            "session_id": session_id,
            "memory": memory,
            "count": len(memory)
        }
    except Exception as e:
        logger.error(f"Memory retrieval failed: {str(e)}", exc_info=True)
        raise
