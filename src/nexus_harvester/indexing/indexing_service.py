"""Indexing service for coordinating backend operations."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel

from nexus_harvester.models import Chunk
from nexus_harvester.clients.zep import ZepClient
from nexus_harvester.clients.mem0 import Mem0Client


# Configure logger
logger = logging.getLogger(__name__)


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
        
        logger.info(
            "IndexingService initialized with backends: Zep, Mem0%s", 
            ", Qdrant (dev)" if use_qdrant_dev else ""
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
        logger.debug("Indexing %d chunks to Zep with session %s", len(chunks), session_id)
        return await self.zep_client.store_memory(session_id, chunks)
    
    async def _index_to_mem0(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Index chunks to Mem0 search.
        
        Args:
            chunks: List of chunks to index
            
        Returns:
            Mem0 indexing result
        """
        logger.debug("Indexing %d chunks to Mem0", len(chunks))
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
            logger.warning("Qdrant indexing requested but no client configured")
            return {"status": "skipped", "reason": "No Qdrant client configured"}
        
        logger.debug("Indexing %d chunks to Qdrant (dev)", len(chunks))
        # Implementation would depend on the actual Qdrant client
        return {"status": "indexed", "count": len(chunks)}
    
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
            logger.error("Error indexing to %s: %s", backend_name, str(result))
            return {"error": str(result), "status": "failed"}
        
        logger.debug("%s indexing successful: %s", backend_name, result)
        return result

# Ensure classes are available for import
__all__ = ["IndexingResult", "IndexingService"]
