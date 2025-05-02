"""Test suite for processing parameter validation in API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError

from nexus_harvester.models import IngestRequest, ProcessingParameters
from nexus_harvester.api.ingest import router, ingest_document
from nexus_harvester.utils.errors import ValidationError as ApiValidationError


@pytest.fixture
def mock_indexing_service():
    """Create a mock indexing service."""
    mock = AsyncMock()
    mock.index_chunks = AsyncMock(return_value={"status": "success"})
    return mock


@pytest.fixture
def mock_background_tasks():
    """Create a mock background task."""
    return MagicMock(spec=BackgroundTasks)


@pytest.fixture
def valid_ingest_request():
    """Create a valid ingest request with content."""
    return IngestRequest(
        url="https://example.com/document",
        title="Test Document",
        source="Test Source"
    )


@pytest.fixture
def valid_ingest_request_with_params():
    """Create a valid ingest request with custom processing parameters."""
    return IngestRequest(
        url="https://example.com/document",
        title="Test Document",
        source="Test Source",
        processing_params=ProcessingParameters(
            chunk_size=1000,
            chunk_overlap=200,
            max_chunks_per_doc=500
        )
    )


@patch("nexus_harvester.api.ingest.DocumentProcessor")
@patch("nexus_harvester.api.ingest.get_settings")
@patch("nexus_harvester.api.ingest.UUID")
@patch("nexus_harvester.api.ingest.update_job_status")
async def test_ingest_with_valid_processing_params(
    mock_update_status, 
    mock_uuid, 
    mock_settings, 
    mock_processor_class,
    valid_ingest_request_with_params,
    mock_background_tasks,
    mock_indexing_service
):
    """Test ingest endpoint with valid custom processing parameters."""
    # Setup mocks
    mock_uuid.return_value = "test-uuid"
    mock_processor = MagicMock()
    mock_processor_class.from_processing_params.return_value = mock_processor
    
    # Mock settings with default values
    mock_settings_instance = MagicMock()
    mock_settings_instance.chunk_size = 512
    mock_settings_instance.chunk_overlap = 128
    mock_settings_instance.max_chunks_per_doc = 1000
    mock_settings.return_value = mock_settings_instance
    
    # Call the ingest endpoint
    response = await ingest_document(
        req=valid_ingest_request_with_params,
        background_tasks=mock_background_tasks,
        content=None,
        settings=mock_settings_instance,
        indexing_service=mock_indexing_service
    )
    
    # Verify response
    assert response.status == "accepted"
    assert response.job_id is not None
    
    # Verify processor was created with custom parameters
    mock_processor_class.from_processing_params.assert_called_once()
    args, kwargs = mock_processor_class.from_processing_params.call_args
    assert args[0] == valid_ingest_request_with_params.processing_params
    
    # Verify background task was added
    mock_background_tasks.add_task.assert_called_once()


@patch("nexus_harvester.api.ingest.DocumentProcessor")
@patch("nexus_harvester.api.ingest.get_settings")
@patch("nexus_harvester.api.ingest.UUID")
@patch("nexus_harvester.api.ingest.update_job_status")
async def test_ingest_with_default_processing_params(
    mock_update_status, 
    mock_uuid, 
    mock_settings, 
    mock_processor_class,
    valid_ingest_request,
    mock_background_tasks,
    mock_indexing_service
):
    """Test ingest endpoint with default processing parameters."""
    # Setup mocks
    mock_uuid.return_value = "test-uuid"
    mock_processor = MagicMock()
    mock_processor_class.return_value = mock_processor
    
    # Mock settings with default values
    mock_settings_instance = MagicMock()
    mock_settings_instance.chunk_size = 512
    mock_settings_instance.chunk_overlap = 128
    mock_settings_instance.max_chunks_per_doc = 1000
    mock_settings.return_value = mock_settings_instance
    
    # Call the ingest endpoint
    response = await ingest_document(
        req=valid_ingest_request,  # No custom processing params
        background_tasks=mock_background_tasks,
        content=None,
        settings=mock_settings_instance,
        indexing_service=mock_indexing_service
    )
    
    # Verify response
    assert response.status == "accepted"
    assert response.job_id is not None
    
    # Verify processor was created with default parameters
    mock_processor_class.assert_called_once_with(
        chunk_size=512,
        chunk_overlap=128,
        max_chunks_per_doc=1000
    )
    
    # Verify background task was added
    mock_background_tasks.add_task.assert_called_once()


@patch("nexus_harvester.api.ingest.DocumentProcessor")
@patch("nexus_harvester.api.ingest.get_settings")
@patch("nexus_harvester.api.ingest.UUID")
@patch("nexus_harvester.api.ingest.update_job_status")
async def test_ingest_with_invalid_processing_params(
    mock_update_status, 
    mock_uuid, 
    mock_settings, 
    mock_processor_class,
    mock_background_tasks,
    mock_indexing_service
):
    """Test ingest endpoint with invalid processing parameters."""
    # Setup mocks
    mock_uuid.return_value = "test-uuid"
    
    # Create a valid request
    valid_request = IngestRequest(
        url="https://example.com/document",
        title="Test Document",
        source="Test Source",
        processing_params=ProcessingParameters(
            chunk_size=500,
            chunk_overlap=200,  # Valid for fixture creation
            max_chunks_per_doc=1000
        )
    )
    
    # Mock validation error in DocumentProcessor
    # This simulates the validation that would happen when the param values are used
    error_message = "Invalid document processing parameters: chunk_overlap: Value error, Chunk overlap must be less than chunk size."
    def side_effect(*args, **kwargs):
        raise ApiValidationError(
            message=error_message,
            details={
                "validation_errors": [
                    {
                        "loc": ["chunk_overlap"],
                        "msg": "Value error, Chunk overlap must be less than chunk size."
                    }
                ],
                "parameters": {
                    "chunk_size": 500,
                    "chunk_overlap": 500,  # Invalid: equal to chunk_size
                    "max_chunks_per_doc": 1000
                }
            }
        )
    
    mock_processor_class.from_processing_params.side_effect = side_effect
    
    # Mock settings with default values
    mock_settings_instance = MagicMock()
    mock_settings_instance.chunk_size = 512
    mock_settings_instance.chunk_overlap = 128
    mock_settings_instance.max_chunks_per_doc = 1000
    mock_settings.return_value = mock_settings_instance
    
    # Call the ingest endpoint and expect exception
    with pytest.raises(ApiValidationError) as exc_info:
        await ingest_document(
            req=valid_request,
            background_tasks=mock_background_tasks,
            content=None,
            settings=mock_settings_instance,
            indexing_service=mock_indexing_service
        )
    
    # Verify error details
    assert "Invalid document processing parameters" in str(exc_info.value)
    assert "chunk_overlap" in str(exc_info.value)
    
    # Verify processor creation was attempted
    mock_processor_class.from_processing_params.assert_called_once()
    
    # Verify background task was NOT added
    mock_background_tasks.add_task.assert_not_called()


@patch("nexus_harvester.api.ingest.DocumentProcessor")
def test_processor_parameters_integration(mock_processor_class):
    """Test the full integration from ProcessingParameters to DocumentProcessor."""
    # Create valid processing parameters
    params = ProcessingParameters(
        chunk_size=1000,
        chunk_overlap=200,
        max_chunks_per_doc=500
    )
    
    # Create processor from params
    from nexus_harvester.processing.document_processor import DocumentProcessor
    # Restore actual implementation for this test
    mock_processor_class.side_effect = DocumentProcessor
    
    processor = DocumentProcessor.from_processing_params(params)
    
    # Verify parameters were properly passed through
    assert processor.chunk_size == 1000
    assert processor.chunk_overlap == 200
    assert processor.max_chunks_per_doc == 500
