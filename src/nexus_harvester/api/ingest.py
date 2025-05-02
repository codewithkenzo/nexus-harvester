"""API endpoints for document ingestion."""

import asyncio
from uuid import UUID, uuid4
from typing import Dict, Any, Optional, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import HttpUrl, BaseModel

from ..models import DocumentMeta, IngestRequest, ProcessingParameters
from ..processing.document_processor import DocumentProcessor
from ..indexing.indexing_service import IndexingService, IndexingResult
from nexus_harvester.clients.utils import fetch_document
from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.api.dependencies import get_settings
from nexus_harvester.utils.errors import (
    InvalidRequestError,
    ResourceNotFoundError,
    DependencyError,
    ValidationError
)
from nexus_harvester.utils.logging import get_logger, bind_component, bind_request_id, bind_doc_id

# Set up logging with component context
logger = get_logger(__name__)
bind_component("api.ingest")

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
    job_data = {
        "status": status,
        "result": result or {}
    }
    _job_store[job_id] = job_data
    
    # Log status update
    logger.debug(
        "Job status updated",
        job_id=job_id,
        status=status,
        has_result=bool(result)
    )
    return job_data


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a job from the job store."""
    job = _job_store.get(job_id)
    
    if not job:
        logger.debug("Job not found", job_id=job_id)
    
    return job


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
    
    # Bind document ID to logging context
    bind_doc_id(doc_id)

    # Validate input: require url OR content
    if not req.url and not content:
        logger.warning(
            "Ingestion request missing required data",
            job_id=job_id,
            doc_id=doc_id,
            has_url=bool(req.url),
            has_content=bool(content)
        )
        raise InvalidRequestError(
            message="Either 'url' in the request body or 'content' query parameter must be provided.",
            details={
                "job_id": job_id,
                "doc_id": doc_id,
                "has_url": bool(req.url),
                "has_content": bool(content)
            }
        )
        
    if req.url and content:
        logger.warning(
            "Both URL and content provided. Content will be ignored, fetching from URL.",
            job_id=job_id,
            doc_id=doc_id,
            url=str(req.url)
        )
        content = None # Prioritize URL if both are given

    # Create document metadata
    doc_meta = DocumentMeta(
        id=doc_id, 
        url=req.url if req.url else "local://content-provided", # Use placeholder if no URL
        title=req.title, 
        source=req.source, 
        metadata=req.metadata
    )
    
    # Handle processing parameters
    processing_params = req.processing_params
    
    # Log processing parameter details
    if processing_params:
        logger.info(
            "Custom processing parameters provided",
            job_id=job_id,
            doc_id=doc_id,
            chunk_size=processing_params.chunk_size,
            chunk_overlap=processing_params.chunk_overlap,
            max_chunks_per_doc=processing_params.max_chunks_per_doc
        )
    else:
        logger.debug(
            "Using default processing parameters",
            job_id=job_id,
            doc_id=doc_id,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_chunks_per_doc=settings.max_chunks_per_doc
        )
        
    # Create processor with validated parameters
    try:
        processor = DocumentProcessor.from_processing_params(processing_params) if processing_params else DocumentProcessor(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_chunks_per_doc=settings.max_chunks_per_doc
        )
    except ValidationError as e:
        logger.error(
            "Processing parameter validation failed",
            job_id=job_id,
            doc_id=doc_id,
            error=str(e),
            details=e.details if hasattr(e, 'details') else None
        )
        # Re-raise with job context
        details = {
            "job_id": job_id,
            "doc_id": doc_id,
        }
        
        # Add additional error details if available
        if hasattr(e, 'details'):
            details.update(e.details)
            
        raise ValidationError(
            message=f"Invalid document processing parameters: {str(e)}",
            details=details
        )

    # Initialize job status
    job_data = update_job_status(
        job_id=job_id, 
        status="pending", 
        result={"doc_id": doc_id}
    )
    
    logger.info(
        "Ingestion job created",
        job_id=job_id,
        doc_id=doc_id,
        title=req.title,
        source=req.source,
        is_url_based=bool(req.url)
    )

    # Start background task
    background_tasks.add_task(
        process_and_index_document,
        job_id=job_id,
        doc_id=UUID(doc_id),
        doc_meta=doc_meta,
        content=content,
        fetch_func=fetch_document,
        processor=processor,
        indexing_service=indexing_service
    )

    return IngestResponse(status="accepted", job_id=job_id, doc_id=doc_id)


@router.get("/status/{job_id}")
async def get_ingestion_status(job_id: str):
    """Get the status of a document ingestion job."""
    logger.info("Getting job status", job_id=job_id)
    
    job = get_job_status(job_id)
    if not job:
        logger.warning("Job status not found", job_id=job_id)
        raise ResourceNotFoundError(
            message=f"Job not found: {job_id}",
            details={"job_id": job_id}
        )
    
    logger.debug("Retrieved job status", job_id=job_id, status=job.get("status"))
    return job


async def process_and_index_document(
    job_id: str, 
    doc_id: UUID, 
    doc_meta: DocumentMeta, 
    content: Optional[str],
    fetch_func: Callable[[HttpUrl], str],
    processor: DocumentProcessor,
    indexing_service: IndexingService,
):
    """Process and index document in background."""
    # Add doc_id to logging context
    bind_doc_id(str(doc_id))
    
    logger.info(
        "Starting background document processing",
        job_id=job_id,
        doc_id=str(doc_id),
        title=doc_meta.title,
        source=doc_meta.source
    )
    
    try:
        # Update job status to processing
        update_job_status(job_id, "processing")
        
        # Fetch content if not provided directly
        if content is None:
            logger.info(
                "Fetching document content",
                job_id=job_id,
                url=str(doc_meta.url)
            )
            try:
                content = await fetch_func(doc_meta.url)
                content_preview = content[:100] + "..." if len(content) > 100 else content
                logger.debug(
                    "Content fetched successfully",
                    job_id=job_id,
                    content_length=len(content),
                    content_preview=content_preview
                )
            except Exception as fetch_error:
                logger.error(
                    "Failed to fetch document content",
                    job_id=job_id,
                    url=str(doc_meta.url),
                    error=str(fetch_error),
                    exc_info=True
                )
                raise DependencyError(
                    message=f"Failed to fetch document from URL: {str(fetch_error)}",
                    details={
                        "job_id": job_id,
                        "doc_id": str(doc_id),
                        "url": str(doc_meta.url),
                        "error": str(fetch_error)
                    }
                )
        else:
            content_preview = content[:100] + "..." if len(content) > 100 else content
            logger.debug(
                "Using provided content",
                job_id=job_id,
                content_length=len(content),
                content_preview=content_preview
            )

        # Process document (chunking)
        logger.info(
            "Processing document into chunks",
            job_id=job_id,
            doc_id=str(doc_id)
        )
        
        try:
            chunks = processor.process_document(doc_meta, content)
            logger.info(
                "Document processed successfully",
                job_id=job_id,
                doc_id=str(doc_id),
                chunk_count=len(chunks)
            )
        except Exception as process_error:
            logger.error(
                "Error processing document",
                job_id=job_id,
                doc_id=str(doc_id),
                error=str(process_error),
                exc_info=True
            )
            update_job_status(job_id, "failed", {"error": f"Processing error: {str(process_error)}"})
            raise
        
        # Index chunks
        logger.info(
            "Indexing document chunks",
            job_id=job_id,
            doc_id=str(doc_id),
            chunk_count=len(chunks)
        )
        update_job_status(job_id, "indexing")
        
        try:
            result: IndexingResult = await indexing_service.index_chunks(
                doc_id=doc_meta.id,
                chunks=chunks
            )
            
            logger.info(
                "Indexing completed successfully",
                job_id=job_id,
                doc_id=str(doc_id),
                index_count=result.indexed_count,
                backends=result.backends
            )
            
            # Update job status with result
            update_job_status(job_id, "completed", result.model_dump())
            
        except Exception as index_error:
            logger.error(
                "Indexing failed",
                job_id=job_id,
                doc_id=str(doc_id),
                error=str(index_error),
                exc_info=True
            )
            update_job_status(job_id, "failed", {"error": f"Indexing error: {str(index_error)}"})
            raise
    
    except Exception as e:
        # Handle any other unexpected errors
        logger.error(
            "Unexpected error during document processing",
            job_id=job_id,
            doc_id=str(doc_id),
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        update_job_status(job_id, "failed", {"error": str(e), "error_type": type(e).__name__})
        
        # No need to re-raise as this is a background task
