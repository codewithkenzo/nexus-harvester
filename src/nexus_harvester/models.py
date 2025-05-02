"""Core data models for the Nexus Harvester."""

from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
import math

from pydantic import BaseModel, Field, ConfigDict, HttpUrl, field_validator, field_serializer


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional document metadata")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        return v


class ProcessingParameters(BaseModel):
    """Parameters for document processing and chunking."""
    model_config = ConfigDict(
        validate_assignment=True,
        extra='forbid',
        str_strip_whitespace=True
    )
    
    chunk_size: int = Field(
        default=512, 
        ge=100,  # Minimum practical chunk size
        le=8192, # Maximum to prevent excessive resource usage
        description="Maximum number of characters in each chunk"
    )
    
    chunk_overlap: int = Field(
        default=128,
        ge=0,    # Minimum overlap
        le=4096, # Upper bound, but still validated against chunk_size
        description="Number of characters that overlap between adjacent chunks"
    )
    
    max_chunks_per_doc: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of chunks allowed per document (for rate limiting)"
    )
    
    # Field serializer for consistent representation
    @field_serializer('chunk_size', 'chunk_overlap', 'max_chunks_per_doc')
    def serialize_int(self, value: int) -> int:
        return value
    
    @field_validator('chunk_overlap')
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        # Get chunk_size from values dict if available
        chunk_size = info.data.get('chunk_size', 512)  # Use default if not available
        
        if v >= chunk_size:
            max_overlap = max(chunk_size - 1, 0)
            raise ValueError(
                f"Chunk overlap ({v}) must be less than chunk size ({chunk_size}). "
                f"Maximum allowed overlap for this chunk size is {max_overlap}."
            )
        
        # Optional stricter validation: overlap should be max 50% of chunk size
        max_reasonable_overlap = math.floor(chunk_size * 0.5)
        if v > max_reasonable_overlap:
            raise ValueError(
                f"Chunk overlap ({v}) exceeds 50% of chunk size ({chunk_size}). "
                f"For optimal processing, overlap should be at most {max_reasonable_overlap} characters."
            )
            
        return v


class IngestRequest(BaseModel):
    """Request model for document ingestion endpoint."""
    model_config = ConfigDict(
        validate_assignment=True,
        extra='forbid'
    )
    
    url: Optional[HttpUrl] = None # Make URL optional
    title: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    processing_params: Optional[ProcessingParameters] = Field(
        default=None,
        description="Optional parameters for document processing and chunking"
    )


class Chunk(BaseModel):
    """Represents a chunk of text from a document."""
    id: UUID = Field(default_factory=uuid4)
    doc_id: UUID
    text: str
    index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
