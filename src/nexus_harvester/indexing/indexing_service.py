"""Indexing service for coordinating backend operations."""

import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel

from nexus_harvester.models import Chunk
from nexus_harvester.clients.zep import ZepClient
from nexus_harvester.clients.mem0 import Mem0Client
from nexus_harvester.utils.logging import get_logger, bind_doc_id, bind_session_id, bind_component

# Configure structured logger
logger = get_logger(__name__)


class IndexingResult(BaseModel):
    """
    Result of indexing a document's chunks.
    """
    doc_id: UUID 
    chunk_count: int
    backends: Dict[str, Dict[str, Any]] 


class IndexingService:
    """
    Service that takes document chunks and pushes them into one or more backends.
    """
    
    def __init__(
        self, 
        zep_client: ZepClient, 
        mem0_client: Mem0Client,
        qdrant_client = None, 
        use_qdrant_dev: bool = False
    ):
        """
        Initialize the IndexingService.
        
        Args:
            zep_client: Client for Zep memory operations
            mem0_client: Client for Mem0 search operations
            qdrant_client: Optional client for Qdrant (development only)
            use_qdrant_dev: Whether to use Qdrant for development
        """
        self.zep_client = zep_client
        self.mem0_client = mem0_client
        self.qdrant_client = qdrant_client
        self.use_qdrant_dev = use_qdrant_dev
        
        # Bind component context for initialization logs
        bind_component("indexing_service")
        
        # Log service initialization with structured data
        backends = ["zep", "mem0"]
        if use_qdrant_dev:
            backends.append("qdrant_dev")
            
        logger.info(
            "IndexingService initialized",
            backends=backends,
            use_qdrant_dev=use_qdrant_dev,
            operation="__init__"
        )
    
    async def index_chunks(
        self, 
        doc_id: UUID, 
        chunks: List[Chunk],
        session_id: Optional[str] = None
    ) -> IndexingResult:
        """
        Index chunks in appropriate backends.
        
        Args:
            doc_id: Document ID
            chunks: List of chunks to index
            session_id: Optional session ID for tracking
            
        Returns:
            Dictionary with indexing results for each backend
        """
        # Use session_id or generate from doc_id
        session_id = session_id or f"doc-{doc_id}"
        
        # Bind context information for all subsequent logs in this call
        bind_doc_id(str(doc_id))
        bind_session_id(session_id)
        bind_component("indexing_service")
        
        logger.info(
            "Started indexing chunks",
            chunk_count=len(chunks),
            doc_id=str(doc_id),
            session_id=session_id,
            operation="index_chunks"
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
        
        return IndexingResult(
            doc_id=doc_id,
            chunk_count=len(chunks),
            backends=backends
        )
    
    async def _index_to_zep(self, session_id: str, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Index chunks to Zep memory.
        
        Args:
            session_id: Session ID for tracking
            chunks: List of chunks to index
            
        Returns:
            Zep indexing result
        """
        logger.debug(
            "Indexing chunks to Zep", 
            backend="zep",
            chunk_count=len(chunks), 
            session_id=session_id,
            operation="_index_to_zep"
        )
        return await self.zep_client.store_memory(session_id, chunks, None)
    
    async def _index_to_mem0(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Index chunks to Mem0 search.
        
        Args:
            chunks: List of chunks to index
            
        Returns:
            Mem0 indexing result
        """
        logger.debug(
            "Indexing chunks to Mem0", 
            backend="mem0",
            chunk_count=len(chunks),
            operation="_index_to_mem0"
        )
        return await self.mem0_client.index_chunks(chunks)
    
    async def _index_to_qdrant(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Index chunks to Qdrant (development only).
        
        Args:
            chunks: List of chunks to index
            
        Returns:
            Qdrant indexing result or error message
        """
        if not self.qdrant_client:
            logger.warning(
                "Qdrant indexing requested but no client configured",
                backend="qdrant",
                operation="_index_to_qdrant",
                status="skipped"
            )
            return {"status": "skipped", "reason": "No Qdrant client configured"}
        
        logger.debug(
            "Indexing chunks to Qdrant (dev)",
            backend="qdrant", 
            chunk_count=len(chunks),
            operation="_index_to_qdrant",
            mode="development"
        )
        # Call the client's index_chunks method
        return await self.qdrant_client.index_chunks(chunks)
    
    def _process_result(self, result: Any, backend_name: str) -> Dict[str, Any]:
        """
        Process and normalize backend results, handling exceptions.
        
        Args:
            result: Result from backend or exception
            backend_name: Name of the backend for logging
            
        Returns:
            Processed result or error information
        """
        if isinstance(result, Exception):
            logger.error(
                "Indexing operation failed", 
                backend=backend_name,
                error=str(result),
                error_type=type(result).__name__,
                status="failed",
                operation="_process_result"
            )
            return {"error": str(result), "status": "failed"}
        
        logger.debug(
            "Indexing operation successful", 
            backend=backend_name,
            status="success",
            operation="_process_result",
            # Avoid logging potentially large result objects
            # result_type=type(result).__name__
        )
        return result

# Ensure classes are available for import
__all__ = ["IndexingResult", "IndexingService"]
