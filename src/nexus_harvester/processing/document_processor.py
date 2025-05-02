"""Document processing and chunking module."""

from typing import List, Dict, Any, Optional
from uuid import UUID
import math

from pydantic import ValidationError as PydanticValidationError

from nexus_harvester.models import DocumentMeta, Chunk, ProcessingParameters
from nexus_harvester.utils.errors import ValidationError
from nexus_harvester.utils.logging import get_logger

# Set up logger
logger = get_logger(__name__)


class DocumentProcessor:
    """Process and chunk documents."""
    def __init__(self, 
                 chunk_size: int = 512, 
                 chunk_overlap: int = 128,
                 max_chunks_per_doc: int = 1000):
        # Create and validate processing parameters using Pydantic model
        try:
            params = ProcessingParameters(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                max_chunks_per_doc=max_chunks_per_doc
            )
            
            # If validation passes, use the validated values
            self.chunk_size = params.chunk_size
            self.chunk_overlap = params.chunk_overlap
            self.max_chunks_per_doc = params.max_chunks_per_doc
            
            logger.debug(
                "DocumentProcessor initialized with validated parameters",
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                max_chunks_per_doc=self.max_chunks_per_doc
            )
            
        except PydanticValidationError as e:
            # Extract the validation errors for better error messages
            error_details = e.errors()
            error_messages = []
            
            # Build a comprehensive error message including all validation details
            for error in error_details:
                loc = error.get('loc', [])
                msg = error.get('msg', '')
                if loc and isinstance(loc, (list, tuple)) and len(loc) > 0:
                    param_name = str(loc[0])
                    error_messages.append(f"{param_name}: {msg}")
                    
            # Create a descriptive error message with full validation details
            error_message = "Invalid document processing parameters: " + "; ".join(error_messages)
            
            logger.error(
                error_message,
                error=str(e),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                max_chunks_per_doc=max_chunks_per_doc
            )
            
            raise ValidationError(
                message=error_message,
                details={
                    "validation_errors": error_details,
                    "parameters": {
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                        "max_chunks_per_doc": max_chunks_per_doc
                    }
                }
            )
    
    @classmethod
    def from_processing_params(cls, params: Optional[ProcessingParameters] = None) -> 'DocumentProcessor':
        """Create a DocumentProcessor from ProcessingParameters object."""
        if params is None:
            # Use defaults if no parameters provided
            return cls()
        
        return cls(
            chunk_size=params.chunk_size,
            chunk_overlap=params.chunk_overlap,
            max_chunks_per_doc=params.max_chunks_per_doc
        )
    
    def process_document(self, doc_meta: DocumentMeta, content: str) -> List[Chunk]:
        """Process document and split into chunks."""
        # Log processing start
        content_length = len(content)
        logger.info(
            "Processing document", 
            doc_id=str(doc_meta.id),
            content_length=content_length,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        
        # Basic chunking strategy - can be replaced with more sophisticated approach
        chunks = []
        text_length = content_length
        start = 0
        
        chunk_index = 0
        while start < text_length:
            # Enforce max chunks limit
            if chunk_index >= self.max_chunks_per_doc:
                logger.warning(
                    "Maximum chunk limit reached, truncating document",
                    doc_id=str(doc_meta.id),
                    max_chunks=self.max_chunks_per_doc,
                    content_length=content_length,
                    processed_length=start
                )
                break
                
            # Calculate chunk boundaries with overlap
            end = min(start + self.chunk_size, text_length)
            chunk_text = content[start:end]
            
            # Create chunk with metadata from document
            chunks.append(Chunk(
                doc_id=doc_meta.id,
                text=chunk_text,
                index=chunk_index,
                metadata={
                    "title": doc_meta.title,
                    "source": doc_meta.source,
                    "url": str(doc_meta.url),
                    # Include chunk position info in metadata
                    "chunk_start": start,
                    "chunk_end": end,
                    "total_chunks": min(math.ceil(text_length / (self.chunk_size - self.chunk_overlap)), 
                                        self.max_chunks_per_doc)
                }
            ))
            
            chunk_index += 1
            if self.chunk_overlap > 0 and end < text_length:  # Apply overlap if not at the end
                start = end - self.chunk_overlap
            else:
                start = end  # No overlap for the last chunk
        
        # Log processing completion
        logger.info(
            "Document processing complete",
            doc_id=str(doc_meta.id),
            total_chunks=len(chunks),
            content_length=content_length
        )
        
        return chunks
