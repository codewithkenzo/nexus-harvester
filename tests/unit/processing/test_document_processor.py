"""Unit tests for document processor validation."""

import pytest
from uuid import uuid4
from datetime import datetime, UTC
from typing import Dict, Any
import math

from pydantic import ValidationError as PydanticValidationError

from nexus_harvester.models import DocumentMeta, ProcessingParameters, Chunk
from nexus_harvester.processing.document_processor import DocumentProcessor
from nexus_harvester.utils.errors import ValidationError


class TestProcessingParameters:
    """Test suite for ProcessingParameters validation."""
    
    def test_valid_parameters(self):
        """Test that valid parameters are accepted."""
        # Standard valid parameters
        params = ProcessingParameters(
            chunk_size=512,
            chunk_overlap=128,
            max_chunks_per_doc=1000
        )
        assert params.chunk_size == 512
        assert params.chunk_overlap == 128
        assert params.max_chunks_per_doc == 1000
        
        # Edge case - minimum values
        params = ProcessingParameters(
            chunk_size=100,  # Minimum valid
            chunk_overlap=0, # Minimum valid
            max_chunks_per_doc=1  # Minimum valid
        )
        assert params.chunk_size == 100
        assert params.chunk_overlap == 0
        assert params.max_chunks_per_doc == 1
        
        # Edge case - maximum values but respecting relationships
        params = ProcessingParameters(
            chunk_size=8192,  # Maximum valid
            chunk_overlap=4000,  # Valid because less than chunk_size and less than 50%
            max_chunks_per_doc=10000  # Maximum valid
        )
        assert params.chunk_size == 8192
        assert params.chunk_overlap == 4000
        assert params.max_chunks_per_doc == 10000
    
    def test_chunk_size_validation(self):
        """Test chunk_size validation constraints."""
        # Too small
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_size=99)  # Below minimum
        
        assert "chunk_size" in str(exc_info.value)
        assert "99" in str(exc_info.value)
        assert "greater than or equal to" in str(exc_info.value).lower()
        
        # Too large
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_size=8193)  # Above maximum
        
        assert "chunk_size" in str(exc_info.value)
        assert "8193" in str(exc_info.value)
        assert "less than or equal to" in str(exc_info.value).lower()
    
    def test_chunk_overlap_validation(self):
        """Test chunk_overlap validation constraints."""
        # Negative overlap
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_overlap=-1)  # Below minimum
        
        assert "chunk_overlap" in str(exc_info.value)
        assert "-1" in str(exc_info.value)
        assert "greater than or equal to" in str(exc_info.value).lower()
        
        # Too large absolute value
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_overlap=4097)  # Above maximum
        
        assert "chunk_overlap" in str(exc_info.value)
        assert "4097" in str(exc_info.value)
        assert "less than or equal to" in str(exc_info.value).lower()
        
        # Overlap greater than chunk size
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_size=500, chunk_overlap=500)
        
        assert "chunk_overlap" in str(exc_info.value)
        assert "must be less than chunk size" in str(exc_info.value).lower()
        
        # Overlap greater than 50% of chunk size
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(chunk_size=500, chunk_overlap=251)
        
        assert "chunk_overlap" in str(exc_info.value)
        assert "exceeds 50% of chunk size" in str(exc_info.value).lower()
        assert "250" in str(exc_info.value)  # Should mention the maximum reasonable overlap
    
    def test_max_chunks_validation(self):
        """Test max_chunks_per_doc validation."""
        # Zero chunks not allowed
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(max_chunks_per_doc=0)
        
        assert "max_chunks_per_doc" in str(exc_info.value)
        assert "0" in str(exc_info.value)
        assert "greater than or equal to" in str(exc_info.value).lower()
        
        # Too many chunks not allowed
        with pytest.raises(PydanticValidationError) as exc_info:
            ProcessingParameters(max_chunks_per_doc=10001)
        
        assert "max_chunks_per_doc" in str(exc_info.value)
        assert "10001" in str(exc_info.value)
        assert "less than or equal to" in str(exc_info.value).lower()


class TestDocumentProcessor:
    """Test suite for DocumentProcessor validation."""
    
    @pytest.fixture
    def sample_doc_meta(self) -> DocumentMeta:
        """Create a sample document metadata for testing."""
        return DocumentMeta(
            id=uuid4(),
            url="https://example.com/test",
            title="Test Document",
            source="Test Source",
            created_at=datetime.now(UTC),
            metadata={"test": "metadata"}
        )
    
    @pytest.fixture
    def sample_content(self) -> str:
        """Create sample document content for testing."""
        # Create content longer than default chunk size
        return "Test content. " * 100  # ~1200 characters
    
    def test_processor_initialization(self):
        """Test processor initialization with valid parameters."""
        # Default initialization
        processor = DocumentProcessor()
        assert processor.chunk_size == 512
        assert processor.chunk_overlap == 128
        assert processor.max_chunks_per_doc == 1000
        
        # Custom initialization
        processor = DocumentProcessor(
            chunk_size=1000,
            chunk_overlap=200,
            max_chunks_per_doc=500
        )
        assert processor.chunk_size == 1000
        assert processor.chunk_overlap == 200
        assert processor.max_chunks_per_doc == 500
    
    def test_processor_initialization_invalid(self):
        """Test processor initialization with invalid parameters."""
        # Invalid chunk size
        with pytest.raises(ValidationError) as exc_info:
            DocumentProcessor(chunk_size=50)  # Too small
        
        assert "Invalid document processing parameters" in str(exc_info.value)
        assert "chunk_size" in str(exc_info.value)
        
        # Invalid overlap vs chunk size relationship
        with pytest.raises(ValidationError) as exc_info:
            DocumentProcessor(chunk_size=500, chunk_overlap=500)  # Equal, not allowed
        
        assert "Invalid document processing parameters" in str(exc_info.value)
        assert "chunk_overlap" in str(exc_info.value)
        assert "must be less than chunk size" in str(exc_info.value)
    
    def test_from_processing_params(self):
        """Test creating processor from ProcessingParameters."""
        # With custom parameters
        params = ProcessingParameters(
            chunk_size=1000,
            chunk_overlap=200,
            max_chunks_per_doc=500
        )
        processor = DocumentProcessor.from_processing_params(params)
        assert processor.chunk_size == 1000
        assert processor.chunk_overlap == 200
        assert processor.max_chunks_per_doc == 500
        
        # With default parameters (None)
        processor = DocumentProcessor.from_processing_params(None)
        assert processor.chunk_size == 512
        assert processor.chunk_overlap == 128
        assert processor.max_chunks_per_doc == 1000
    
    def test_process_document_basic(self, sample_doc_meta, sample_content):
        """Test basic document processing functionality."""
        processor = DocumentProcessor(chunk_size=200, chunk_overlap=50)
        chunks = processor.process_document(sample_doc_meta, sample_content)
        
        # Verify chunks were created
        assert len(chunks) > 0
        
        # Verify first chunk
        assert isinstance(chunks[0], Chunk)
        assert chunks[0].doc_id == sample_doc_meta.id
        assert len(chunks[0].text) <= 200  # Should not exceed chunk size
        assert chunks[0].index == 0
        
        # Verify metadata was properly attached
        assert chunks[0].metadata.get("title") == sample_doc_meta.title
        assert chunks[0].metadata.get("source") == sample_doc_meta.source
        assert chunks[0].metadata.get("url") == str(sample_doc_meta.url)
        
        # Verify chunk positioning information
        assert "chunk_start" in chunks[0].metadata
        assert "chunk_end" in chunks[0].metadata
        assert "total_chunks" in chunks[0].metadata
    
    def test_max_chunks_limit(self, sample_doc_meta):
        """Test that max_chunks_per_doc is enforced."""
        # Create a long document
        long_content = "Test content. " * 1000  # ~12000 characters
        
        # Set a low max_chunks limit
        processor = DocumentProcessor(
            chunk_size=100,
            chunk_overlap=0,
            max_chunks_per_doc=5
        )
        
        # Process document
        chunks = processor.process_document(sample_doc_meta, long_content)
        
        # Verify chunks were limited
        assert len(chunks) == 5  # Should be exactly the max limit
        
        # Verify the last chunk has the correct index
        assert chunks[-1].index == 4  # 0-based indexing, so last index is 4
    
    def test_chunk_overlap_applied(self, sample_doc_meta):
        """Test that chunk overlap is properly applied."""
        # Create content that will generate at least 3 chunks
        content = "ABCDEFGHIJ" * 100  # 1000 characters
        
        # Process with significant overlap
        processor = DocumentProcessor(
            chunk_size=400, 
            chunk_overlap=200,  # 50% overlap
            max_chunks_per_doc=10
        )
        
        chunks = processor.process_document(sample_doc_meta, content)
        
        # Verify at least 3 chunks were created
        assert len(chunks) >= 3
        
        # Calculate expected chunk boundaries
        # First chunk: 0-400
        # Second chunk: 200-600 (overlap: 200-400)
        # Third chunk: 400-800 (overlap: 400-600)
        
        # Verify overlapping content (check chunk metadata for position info)
        chunk1_end = chunks[0].metadata["chunk_end"]
        chunk2_start = chunks[1].metadata["chunk_start"]
        
        # Verify overlap
        assert chunk2_start < chunk1_end
        assert (chunk1_end - chunk2_start) == 200  # Should be exactly the overlap amount
