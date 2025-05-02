"""Core data models for the Nexus Harvester."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict, HttpUrl, field_validator


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
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional document metadata")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        return v


class IngestRequest(BaseModel):
    """Request model for document ingestion endpoint."""
    url: Optional[HttpUrl] = None # Make URL optional
    title: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """Represents a chunk of text from a document."""
    id: UUID = Field(default_factory=uuid4)
    doc_id: UUID
    text: str
    index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
