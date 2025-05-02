"""API endpoints for document ingestion."""

import asyncio
from uuid import UUID, uuid4
from typing import Dict, Any, Optional, Callable
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import HttpUrl, BaseModel

from ..models import DocumentMeta, IngestRequest
from ..processing.document_processor import DocumentProcessor
from ..indexing.indexing_service import IndexingService, IndexingResult
from nexus_harvester.clients.utils import fetch_document
from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.api.dependencies import get_settings

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["Ingestion"])

# --- Pydantic Models for API --- 

class IngestResponse(BaseModel):
    """Response model for successful ingestion requests."""
    status: str = "accepted"
    job_id: str
    doc_id: str

class JobStatusResponse(BaseModel):
    """Response model for job status requests."""
    status: str
    result: Optional[Dict[str, Any]] = None

# In-memory job storage (replace with a proper storage solution in production)
_job_store: Dict[str, Dict[str, Any]] = {}


def update_job_status(job_id: str, status: str, result: Dict[str, Any] = None) -> None:
    """Update the status of a job in the job store."""
    _job_store[job_id] = {
        "status": status,
        "result": result or {}
    }


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a job from the job store."""
    return _job_store.get(job_id)


def get_indexing_service() -> IndexingService:
    """Get the indexing service instance."""
    from nexus_harvester.api.dependencies import get_indexing_service as get_service
    return get_service()


@router.post("/ingest/", 
             response_model=IngestResponse, 
             status_code=status.HTTP_202_ACCEPTED,
             summary="Ingest a document by URL or content")
async def ingest_document(
    req: IngestRequest, 
    background_tasks: BackgroundTasks, 
    content: Optional[str] = Query(None, description="Document content (alternative to URL)"),
    settings: KnowledgeHarvesterSettings = Depends(get_settings),
    indexing_service: IndexingService = Depends(get_indexing_service)
):
    """
    Accepts document metadata (URL or content) and starts background processing.

    - Provide either `url` in the request body or `content` as a query parameter.
    """
    job_id = str(uuid4())
    doc_id = str(uuid4())

    # Validate input: require url OR content
    if not req.url and not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'url' in the request body or 'content' query parameter must be provided."
        )
    if req.url and content:
        print("[WARN] Both URL and content provided. Content will be ignored, fetching from URL.")
        content = None # Prioritize URL if both are given

    # Create DocumentMeta from request
    doc_meta = DocumentMeta(
        id=doc_id, 
        url=req.url if req.url else "local://content-provided", # Use placeholder if no URL
        title=req.title, 
        source=req.source, 
        metadata=req.metadata
    )

    # Initialize job status
    _job_store[job_id] = { "status": "pending", "doc_id": doc_id }
    print(f"[API] Job {job_id} created for doc {doc_id}")

    # Add background task
    print(f"[API] Adding background task for job {job_id}")
    background_tasks.add_task(
        process_and_index_document, 
        job_id=job_id, 
        doc_id=doc_id,
        doc_meta=doc_meta, 
        content=content, # Pass content (if any) to the task
        fetch_func=fetch_document, 
        processor=DocumentProcessor(), # Instantiate here or depend?
        indexing_service=indexing_service
    )

    return IngestResponse(status="accepted", job_id=job_id, doc_id=doc_id)


@router.get("/status/{job_id}")
async def get_ingestion_status(job_id: str):
    """Get the status of a document ingestion job."""
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )
    
    return job


async def process_and_index_document(
    job_id: str, 
    doc_id: UUID, 
    doc_meta: DocumentMeta, 
    content: Optional[str], # Add content parameter
    fetch_func: Callable[[HttpUrl], str],
    processor: DocumentProcessor,
    indexing_service: IndexingService,
):
    """Process and index document in background."""
    print(f"\n[BG TASK {job_id}] Starting processing for {doc_meta.id}")
    try:
        logger.info(f"Processing document: {doc_meta.title} (ID: {doc_meta.id})")
        update_job_status(job_id, "processing")
        print(f"[BG TASK {job_id}] Status updated to processing")
        
        # Fetch content if not provided directly
        if content is None:
            print(f"[BG TASK {job_id}] Fetching content from {doc_meta.url}")
            content = await fetch_func(doc_meta.url)
            print(f"[BG TASK {job_id}] Content fetched: {content[:100]}...") # Log snippet
        else:
            print(f"[BG TASK {job_id}] Using provided content: {content[:100]}...")

        # Process document (synchronous)
        print(f"[BG TASK {job_id}] Instantiating DocumentProcessor") # Should already be instantiated
        # processor = DocumentProcessor() # Don't reinstantiate if passed in
        chunks = processor.process_document(doc_meta, content)
        print(f"[BG TASK {job_id}] processor.process_document completed. Found {len(chunks)} chunks.")
        print(f"[BG TASK {job_id}] Document processed into {len(chunks)} chunks")
        
        # Index chunks
        logger.info(f"Indexing {len(chunks)} chunks for document: {doc_meta.title}")
        update_job_status(job_id, "indexing")
        print(f"[BG TASK {job_id}] Getting indexing service")
        result: IndexingResult = await indexing_service.index_chunks(
            doc_id=doc_meta.id,
            chunks=chunks
        )
        print(f"[BG TASK {job_id}] Indexing completed. Result: {result}")
        
        # Update job status
        logger.info(f"Completed processing document: {doc_meta.title}")
        update_job_status(job_id, "completed", result.model_dump()) # Dump model to dict for storage
        print(f"[BG TASK {job_id}] Job status updated to completed")
    
    except Exception as e:
        # Handle errors
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        print(f"[BG TASK {job_id}] Exception occurred: {str(e)}")
        update_job_status(job_id, "failed", {"error": str(e)})
        print(f"[BG TASK {job_id}] Job status updated to failed")
