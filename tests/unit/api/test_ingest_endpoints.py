"""Unit tests for the document ingestion API endpoints."""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock, Mock
from typing import Dict, Any

import pytest
from fastapi import FastAPI, status, BackgroundTasks, Depends, HTTPException
from fastapi.testclient import TestClient
from httpx import AsyncClient
from pydantic import HttpUrl, SecretStr

from nexus_harvester.models import DocumentMeta, Chunk, IngestRequest
from nexus_harvester.api.ingest import (
    IngestResponse,
    JobStatusResponse,
    process_and_index_document,
    router
)
from nexus_harvester.clients.utils import fetch_document
from nexus_harvester.indexing.indexing_service import IndexingService, IndexingResult
from nexus_harvester.processing.document_processor import DocumentProcessor
from nexus_harvester.settings import KnowledgeHarvesterSettings
from nexus_harvester.api.dependencies import get_settings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    mock = MagicMock(spec=KnowledgeHarvesterSettings)
    # Set required attributes with test values
    mock.zep_api_url = HttpUrl("http://test-zep.example.com")
    mock.zep_api_key = MagicMock(spec=SecretStr)
    mock.zep_api_key.get_secret_value.return_value = "test-zep-key"
    mock.mem0_api_url = HttpUrl("http://test-mem0.example.com")
    mock.mem0_api_key = MagicMock(spec=SecretStr)
    mock.mem0_api_key.get_secret_value.return_value = "test-mem0-key"
    mock.use_qdrant_dev = False
    mock.chunk_size = 512
    mock.chunk_overlap = 128
    return mock

@pytest.fixture
def app(mock_background_tasks, mock_settings):
    """Create a test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    
    # Override the dependencies
    app.dependency_overrides[BackgroundTasks] = lambda: mock_background_tasks
    app.dependency_overrides[get_settings] = lambda: mock_settings
    
    # We'll mock fetch_document in individual tests for more control
    yield app
    
    # Clean up dependency overrides
    app.dependency_overrides = {}


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    """Create an async test client for the FastAPI application."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_doc_meta():
    """Create a valid document metadata object."""
    return {
        "url": "https://example.com/document",
        "title": "Test Document",
        "source": "test",
        "metadata": {"author": "Test Author", "category": "Test"}
    }


@pytest.fixture
def mock_background_tasks():
    """Create a mock BackgroundTasks object."""
    mock = MagicMock(spec=BackgroundTasks)
    # Ensure add_task method exists and returns None
    mock.add_task = MagicMock(return_value=None)
    return mock


@pytest.fixture
def mock_processor():
    """Mock document processor."""
    processor = AsyncMock()
    processor.process_document.return_value = [
        MagicMock(id=uuid.uuid4(), doc_id=uuid.uuid4(), text="Test chunk", index=0)
    ]
    return processor


@pytest.fixture
def mock_indexing_service():
    """Mock indexing service."""
    service = AsyncMock()
    service.index_chunks.return_value = {
        "doc_id": str(uuid.uuid4()),
        "chunk_count": 1,
        "backends": {
            "zep": {"status": "success"},
            "mem0": {"status": "indexed"}
        }
    }
    return service


class TestIngestEndpoints:
    """Test suite for document ingestion endpoints."""
    
    def test_debug(self, client, valid_doc_meta, mock_background_tasks):
        """Simplified test to debug the issue."""
        print("\n[DEBUG] Starting simplified debug test")
        
        # Create a simple mock for fetch_document
        mock_fetch = AsyncMock(return_value="Mocked content")
        
        # Print the routes available in the app
        print("[DEBUG] Available routes:")
        for route in client.app.routes:
            print(f"[DEBUG] Route: {route.path} - {route.methods}")
        
        # Patch fetch_document and make a simple request
        with patch("nexus_harvester.api.ingest.fetch_document", mock_fetch):
            print("[DEBUG] Making request to /ingest/")
            response = client.post("/ingest/", json=valid_doc_meta)
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response body: {response.json() if response.status_code < 400 else response.text}")
            print("[DEBUG] Test completed")
            
            # Basic assertion
            assert response.status_code == status.HTTP_202_ACCEPTED

    def test_ingest_document_success(self, client, valid_doc_meta, mock_background_tasks, mock_processor, mock_indexing_service):
        """Test successful document ingestion via URL."""
        # Arrange - Prepare request data
        request_data = {
            "url": str(valid_doc_meta['url']),
            "title": valid_doc_meta['title'],
            "source": valid_doc_meta['source'],
            "metadata": valid_doc_meta['metadata']
        }
        
        print("[DEBUG] Setting up mocks")
        mock_fetch = AsyncMock(return_value="Mocked document content")
        with (
            patch("nexus_harvester.api.ingest.fetch_document", mock_fetch),
            patch("nexus_harvester.api.ingest.DocumentProcessor", return_value=mock_processor),
            patch("nexus_harvester.api.ingest.get_indexing_service", return_value=mock_indexing_service)
        ):
            
            # Override BackgroundTasks dependency
            client.app.dependency_overrides[BackgroundTasks] = lambda: mock_background_tasks
            
            # Act
            print("[DEBUG] Making request to /ingest/")
            print(f"[DEBUG] Request payload: {request_data}")
            response = client.post("/ingest/", json=request_data)
            
            # Clean up overrides
            client.app.dependency_overrides = {}
            
            # Assert
            print(f"[DEBUG] Response status code: {response.status_code}")
            print(f"[DEBUG] Response body: {response.json()}")
            response_json = response.json()
            assert response_json["status"] == "accepted"
            assert "job_id" in response_json
            job_id = response_json["job_id"]
            doc_id = response_json["doc_id"]

            # Check background task was added with correct args
            mock_background_tasks.add_task.assert_called_once()
            args, kwargs = mock_background_tasks.add_task.call_args
            assert args[0] == process_and_index_document
            assert kwargs['job_id'] == job_id
            assert kwargs['doc_id'] == doc_id
            assert isinstance(kwargs['doc_meta'], DocumentMeta)
            assert kwargs['doc_meta'].url == valid_doc_meta['url']
            assert kwargs['content'] is None # Content is None when URL is provided
            assert kwargs['fetch_func'] is fetch_document
            assert isinstance(kwargs['processor'], DocumentProcessor)
            assert kwargs['indexing_service'] is mock_indexing_service

            print("[DEBUG] Test completed successfully")

    def test_ingest_document_with_content(self, client, valid_doc_meta, mock_background_tasks, mock_processor):
        """Test document ingestion with content provided."""
        # Arrange
        content = "This is the document content."
        request_data = { # No URL in request body
            "title": valid_doc_meta['title'],
            "source": valid_doc_meta['source'],
            "metadata": valid_doc_meta['metadata']
        }
        mock_indexing_service = AsyncMock(spec=IndexingService)
        mock_indexing_service.index_chunks.return_value = IndexingResult(
            doc_id=valid_doc_meta['id'], 
            chunk_count=1, 
            backends={"mock": {"status": "success"}}
        )
        mock_fetch = AsyncMock(return_value="Should not be called")
        
        # Mock fetch_document to avoid real HTTP requests
        # and provide processor mock
        with patch("nexus_harvester.api.ingest.fetch_document", mock_fetch), \
             patch("nexus_harvester.api.ingest.DocumentProcessor", return_value=mock_processor), \
             patch("nexus_harvester.api.ingest.get_indexing_service", return_value=mock_indexing_service):
            # Added processor patch and indexing service mock
            
            # Override BackgroundTasks dependency
            client.app.dependency_overrides[BackgroundTasks] = lambda: mock_background_tasks
            
            # Act
            response = client.post(
                "/ingest/", 
                json=request_data, # Use request_data
                params={"content": content}
            )
            
            # Clean up overrides
            client.app.dependency_overrides = {}

            # Assert
            assert response.status_code == status.HTTP_202_ACCEPTED
            
            # Verify background task was added with the correct content
            mock_background_tasks.add_task.assert_called_once()
            args, kwargs = mock_background_tasks.add_task.call_args
            assert kwargs['content'] == content
            
            # Verify fetch_document was not called
            mock_fetch.assert_not_called()

    def test_ingest_document_invalid_url(self, client, valid_doc_meta):
        """Test document ingestion with invalid URL."""
        # Arrange
        valid_doc_meta["url"] = "invalid-url"
        
        # Create a mock for fetch_document - should not be called due to validation error
        mock_fetch = AsyncMock(return_value="Should not be called")
        
        # Mock fetch_document to avoid real HTTP requests
        with patch("nexus_harvester.api.ingest.fetch_document", mock_fetch):
            # Act
            response = client.post("/ingest/", json=valid_doc_meta)
            
            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            assert "url" in response.json()["detail"][0]["loc"]
            
            # Verify fetch_document was not called
            mock_fetch.assert_not_called()

    def test_ingest_document_missing_required_fields(self, client):
        """Test document ingestion with missing required fields."""
        # Arrange
        incomplete_doc = {}
        
        # Create a mock for fetch_document - should not be called due to validation error
        mock_fetch = AsyncMock(return_value="Should not be called")
        
        # Mock fetch_document to avoid real HTTP requests
        with patch("nexus_harvester.api.ingest.fetch_document", mock_fetch):
            # Act
            response = client.post("/ingest/", json=incomplete_doc)
            
            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            fields = [field["loc"][1] for field in response.json()["detail"]]
            assert "url" in fields
            assert "title" in fields
            assert "source" in fields
            
            # Verify fetch_document was not called
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_and_index_document(
        self,
        valid_doc_meta,
        mock_fetch,
        mock_processor,
        mock_indexing_service,
    ):
        """Test the background task logic directly."""
        # Arrange
        job_id = "test_job_direct"
        # Create DocumentMeta instance for the test
        doc_meta_obj = DocumentMeta(
            id=valid_doc_meta['id'],
            url=valid_doc_meta['url'],
            title=valid_doc_meta['title'],
            source=valid_doc_meta['source'],
            metadata=valid_doc_meta['metadata']
        )
        doc_id = doc_meta_obj.id

        # Patch update_job_status
        with patch("nexus_harvester.api.ingest.update_job_status") as mock_update_status:
            # Act
            await process_and_index_document(
                job_id=job_id,
                doc_id=doc_id,
                doc_meta=doc_meta_obj, # Pass DocumentMeta obj
                content=None, # Pass content (None here)
                fetch_func=mock_fetch, # Pass the mock fetch directly
                processor=mock_processor,
                indexing_service=mock_indexing_service,
            )

            # Assert
            # Check mocks were called
            mock_fetch.assert_called_once_with(doc_meta_obj.url) # Use obj attribute
            mock_processor.process_document.assert_called_once()
            mock_indexing_service.index_chunks.assert_called_once()
            # Check status updates
            assert mock_update_status.call_count == 2
            mock_update_status.assert_any_call(job_id, "processing")
            mock_update_status.assert_called_with(job_id, "completed")

    @pytest.mark.asyncio
    async def test_process_and_index_document_error_handling(
        self,
        valid_doc_meta,
        mock_fetch,
        mock_processor,
        mock_indexing_service,
    ):
        """Test error handling in the background document processing function."""
        # Arrange
        job_id = "test_job_error"
        # Create DocumentMeta instance
        doc_meta_obj = DocumentMeta(
            id=valid_doc_meta['id'],
            url=valid_doc_meta['url'],
            title=valid_doc_meta['title'],
            source=valid_doc_meta['source'],
            metadata=valid_doc_meta['metadata']
        )
        doc_id = doc_meta_obj.id
        mock_fetch.side_effect = Exception("Fetch failed")

        # Patch update_job_status
        with patch("nexus_harvester.api.ingest.update_job_status") as mock_update_status:
            # Act
            await process_and_index_document(
                job_id=job_id,
                doc_id=doc_id,
                doc_meta=doc_meta_obj, # Pass DocumentMeta obj
                content=None, # Pass content (None here)
                fetch_func=mock_fetch, # Pass the mock fetch directly
                processor=mock_processor,
                indexing_service=mock_indexing_service,
            )

            # Assert
            mock_fetch.assert_called_once_with(doc_meta_obj.url) # Use obj attribute
            mock_processor.process_document.assert_not_called()
            mock_indexing_service.index_chunks.assert_not_called()
            # Check status updates
            assert mock_update_status.call_count == 2
            mock_update_status.assert_any_call(job_id, "processing")
            mock_update_status.assert_called_with(job_id, "failed")

    def test_get_job_status(self, client):
        """Test retrieving job status."""
        # Arrange
        job_id = "existing_job"
        job_status = {
            "status": "completed",
            "result": {
                "doc_id": str(uuid.uuid4()),
                "chunk_count": 5
            }
        }
        
        # Mock get_job_status to return our test data
        with patch("nexus_harvester.api.ingest.get_job_status", return_value=job_status):
            # Act
            response = client.get(f"/ingest/status/{job_id}")
            
            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.json() == job_status

    def test_get_job_status_not_found(self, client):
        """Test retrieving status for a non-existent job."""
        # Arrange
        job_id = "non_existent_job"
        
        # Mock get_job_status to return None (job not found)
        with patch("nexus_harvester.api.ingest.get_job_status", return_value=None):
            # Act
            response = client.get(f"/ingest/status/{job_id}")
            
            # Assert
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Job not found" in response.json()["detail"]
