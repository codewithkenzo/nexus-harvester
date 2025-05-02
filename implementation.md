# Knowledge Harvester Implementation Guide

## Core Components

### 1. FastAPI Application

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import orjson
from pydantic import BaseModel, field_validator
from fastapi.responses import ORJSONResponse

# Initialize FastAPI with orjson for better performance
app = FastAPI(
    title="Knowledge Harvester API",
    description="API for document ingestion and retrieval",
    version="1.0.0",
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
```

### 2. Core Data Models

```python
from pydantic import BaseModel, field_validator, ConfigDict, HttpUrl
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID, uuid4

class DocumentMeta(BaseModel):
    """Document metadata for ingestion."""
    model_config = ConfigDict(
        validate_assignment=True,
        extra='forbid',
        str_strip_whitespace=True
    )
    
    id: UUID = Field(default_factory=uuid4)
    url: HttpUrl
    title: str
    source: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        return v

class Chunk(BaseModel):
    """Document chunk model."""
    id: UUID = Field(default_factory=uuid4)
    doc_id: UUID
    text: str
    index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
```

### 3. Backend Clients

#### Zep Client

```python
from typing import List, Dict, Any
import httpx
from pydantic import BaseModel, SecretStr

class ZepClient:
    """Client for Zep memory operations."""
    def __init__(self, api_url: str, api_key: SecretStr):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers)
    
    async def store_memory(self, session_id: str, chunks: List[Chunk], 
                          metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Store chunks in Zep memory."""
        payload = {
            "session_id": session_id,
            "chunks": [chunk.model_dump() for chunk in chunks],
            "metadata": metadata or {}
        }
        response = await self.client.post(
            f"{self.api_url}/memory",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def get_memory(self, session_id: str, 
                         limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve memory for a session."""
        response = await self.client.get(
            f"{self.api_url}/memory/{session_id}",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()
```

#### Mem0 Client

```python
from typing import List, Dict, Any
import httpx
from pydantic import BaseModel, SecretStr

class Mem0Client:
    """Client for Mem0 search operations."""
    def __init__(self, api_url: str, api_key: SecretStr):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers)
    
    async def index_chunks(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """Index chunks in Mem0."""
        payload = {
            "chunks": [chunk.model_dump() for chunk in chunks]
        }
        response = await self.client.post(
            f"{self.api_url}/index",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def search(self, query: str, filters: Dict[str, Any] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
        """Search indexed chunks."""
        payload = {
            "query": query,
            "filters": filters or {},
            "limit": limit
        }
        response = await self.client.post(
            f"{self.api_url}/search",
            json=payload
        )
        response.raise_for_status()
        return response.json()
```

### 4. Pipeline Components

#### Document Processor

```python
from typing import List
import asyncio
from uuid import UUID

class DocumentProcessor:
    """Process and chunk documents."""
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    async def process_document(self, doc_meta: DocumentMeta, content: str) -> List[Chunk]:
        """Process document and split into chunks."""
        # Basic chunking strategy - replace with more sophisticated approach
        chunks = []
        text_length = len(content)
        start = 0
        
        chunk_index = 0
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_text = content[start:end]
            
            chunks.append(Chunk(
                doc_id=doc_meta.id,
                text=chunk_text,
                index=chunk_index,
                metadata={
                    "title": doc_meta.title,
                    "source": doc_meta.source,
                    "url": str(doc_meta.url)
                }
            ))
            
            chunk_index += 1
            start = end - self.chunk_overlap
        
        return chunks
```

#### Indexing Service

```python
from typing import List, Dict, Any
import asyncio
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

class IndexingService:
    """Coordinate indexing to backend services."""
    def __init__(self, zep_client: ZepClient, mem0_client: Mem0Client, 
                qdrant_client = None, use_qdrant_dev: bool = False):
        self.zep_client = zep_client
        self.mem0_client = mem0_client
        self.qdrant_client = qdrant_client
        self.use_qdrant_dev = use_qdrant_dev
        
        # Log initialization
        logger.info(
            "IndexingService initialized with backends: Zep, Mem0%s", 
            ", Qdrant (dev)" if use_qdrant_dev else ""
        )
    
    async def index_chunks(self, doc_id: UUID, chunks: List[Chunk], 
                           session_id: str = None) -> Dict[str, Any]:
        """Index chunks in appropriate backends."""
        # Use session_id or generate from doc_id
        session_id = session_id or f"doc-{doc_id}"
        
        logger.info(
            "Indexing %d chunks for document %s with session %s", 
            len(chunks), doc_id, session_id
        )
        
        # Create tasks for parallel processing
        zep_task = self._index_to_zep(session_id, chunks)
        mem0_task = self._index_to_mem0(chunks)
        qdrant_task = self._index_to_qdrant(chunks) if self.use_qdrant_dev else asyncio.sleep(0)
        
        # Process in parallel
        results = await asyncio.gather(
            zep_task, mem0_task, qdrant_task, 
            return_exceptions=True  # Don't let one failure stop others
        )
        
        # Process results, handling any exceptions
        backends = {
            "zep": self._process_result(results[0], "Zep"),
            "mem0": self._process_result(results[1], "Mem0"),
        }
        
        if self.use_qdrant_dev:
            backends["qdrant"] = self._process_result(results[2], "Qdrant")
        
        return {
            "doc_id": str(doc_id),
            "chunk_count": len(chunks),
            "backends": backends
        }
    
    async def _index_to_zep(self, session_id: str, chunks: List[Chunk]) -> Dict[str, Any]:
        """Index chunks to Zep memory."""
        logger.debug("Indexing %d chunks to Zep with session %s", len(chunks), session_id)
        return await self.zep_client.store_memory(session_id, chunks, None)
    
    async def _index_to_mem0(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """Index chunks to Mem0 search."""
        logger.debug("Indexing %d chunks to Mem0", len(chunks))
        return await self.mem0_client.index_chunks(chunks)
    
    async def _index_to_qdrant(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """Index chunks to Qdrant (development only)."""
        if not self.qdrant_client:
            logger.warning("Qdrant indexing requested but no client configured")
            return {"status": "skipped", "reason": "No Qdrant client configured"}
        
        logger.debug("Indexing %d chunks to Qdrant (dev)", len(chunks))
        # Call the client's index_chunks method
        return await self.qdrant_client.index_chunks(chunks)
        
    def _process_result(self, result: Any, backend_name: str) -> Dict[str, Any]:
        """Process and normalize backend results, handling exceptions."""
        if isinstance(result, Exception):
            logger.error("Error indexing to %s: %s", backend_name, str(result))
            return {"error": str(result), "status": "failed"}
        
        logger.debug("%s indexing successful: %s", backend_name, result)
        return result

## API Endpoints

### 1. Document Ingestion

```python
from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from uuid import UUID

@app.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    doc_meta: DocumentMeta,
    background_tasks: BackgroundTasks,
    content: str = None,
    session_id: str = None
):
    """
    Ingest a document for processing and indexing.
    
    If content is not provided, the document will be fetched from the URL.
    """
    # Generate job_id
    job_id = str(uuid4())
    
    # Register background task
    background_tasks.add_task(
        process_and_index_document,
        job_id=job_id,
        doc_meta=doc_meta,
        content=content,
        session_id=session_id
    )
    
    return {
        "status": "accepted",
        "job_id": job_id,
        "doc_id": str(doc_meta.id)
    }

async def process_and_index_document(
    job_id: str,
    doc_meta: DocumentMeta,
    content: str = None,
    session_id: str = None
):
    """Process and index document in background."""
    try:
        # Fetch content if not provided
        if not content:
            content = await fetch_document(doc_meta.url)
        
        # Process into chunks
        processor = DocumentProcessor()
        chunks = await processor.process_document(doc_meta, content)
        
        # Index chunks
        indexing_service = get_indexing_service()
        result = await indexing_service.index_chunks(
            doc_id=doc_meta.id,
            chunks=chunks,
            session_id=session_id
        )
        
        # Update job status
        update_job_status(job_id, "completed", result)
    
    except Exception as e:
        # Handle errors
        update_job_status(job_id, "failed", {"error": str(e)})
        raise
```

### 2. Search Endpoint

```python
from fastapi import Query, Depends, HTTPException
from typing import List, Dict, Any

@app.get("/search")
async def search_documents(
    query: str = Query(..., description="Search query"),
    filters: Dict[str, Any] = None,
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return")
):
    """Search indexed documents."""
    try:
        # Get Mem0 client
        mem0_client = get_mem0_client()
        
        # Execute search
        results = await mem0_client.search(
            query=query,
            filters=filters,
            limit=limit
        )
        
        return {
            "query": query,
            "results": results,
            "count": len(results)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )
```

### 3. Streaming Search

```python
from fastapi import Query, Depends
from fastapi.responses import StreamingResponse
import asyncio
import orjson

@app.get("/search/stream")
async def stream_search(
    query: str = Query(..., description="Search query"),
    filters: Dict[str, Any] = None,
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return")
):
    """Stream search results as SSE."""
    
    async def event_generator():
        """Generate SSE events for search results."""
        # Initial response
        yield f"data: {orjson.dumps({'status': 'processing'}).decode()}\n\n"
        
        try:
            # Get Mem0 client
            mem0_client = get_mem0_client()
            
            # Execute search
            results = await mem0_client.search(
                query=query,
                filters=filters,
                limit=limit
            )
            
            # Stream results
            for result in results:
                yield f"data: {orjson.dumps(result).decode()}\n\n"
                await asyncio.sleep(0.05)  # Small delay for smooth streaming
            
            # Final event
            yield f"data: {orjson.dumps({'status': 'complete', 'total': len(results)}).decode()}\n\n"
        
        except Exception as e:
            # Error event
            yield f"data: {orjson.dumps({'status': 'error', 'message': str(e)}).decode()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

## MCP Integration

### MCP Server Setup

```python
from fastmcp import MCPServer, mcp
from pydantic import BaseModel, Field
from typing import List, Dict, Any

# MCP request/response models
class IngestRequest(BaseModel):
    url: HttpUrl
    title: str
    source: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestResponse(BaseModel):
    doc_id: str
    job_id: str
    status: str

class SearchRequest(BaseModel):
    query: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)

class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    query: str
    count: int

# Define MCP tools
@mcp.tool(name="ingest_document", description="Ingest a document for processing")
async def ingest_document_tool(request: IngestRequest) -> IngestResponse:
    """Ingest a document via MCP."""
    # Convert to DocumentMeta
    doc_meta = DocumentMeta(
        url=request.url,
        title=request.title,
        source=request.source,
        metadata=request.metadata
    )
    
    # Process document
    job_id = str(uuid4())
    background_tasks.add_task(
        process_and_index_document,
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

# Create and start MCP server
mcp_server = MCPServer(
    name="knowledge-harvester",
    description="Knowledge harvesting and retrieval service",
    version="1.0.0"
)

mcp_server.add_tool(ingest_document_tool)
mcp_server.add_tool(search_knowledge_tool)
```

## Dependency Injection

```python
from fastapi import Depends
from functools import lru_cache

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
```

## Main Application

```python
import uvicorn

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Knowledge Harvester API",
        description="API for document ingestion and retrieval",
        version="1.0.0",
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
    from .api.ingest import router as ingest_router
    from .api.search import router as search_router
    
    app.include_router(ingest_router, prefix="/ingest", tags=["Ingestion"])
    app.include_router(search_router, prefix="/search", tags=["Search"])
    
    # Health check
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "healthy"}
    
    return app

if __name__ == "__main__":
    # Get settings
    settings = get_settings()
    
    # Create app
    app = create_app()
    
    # Start MCP server in a separate thread
    import threading
    threading.Thread(
        target=mcp_server.serve_http,
        kwargs={"host": settings.host, "port": settings.mcp_port},
        daemon=True
    ).start()
    
    # Start FastAPI
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port
    )
``` 