"""Unit tests for MCP tools."""

import uuid
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any, List

import pytest
from pydantic import BaseModel, HttpUrl

from nexus_harvester.models import DocumentMeta, Chunk
from nexus_harvester.mcp.tools import (
    IngestRequest, 
    IngestResponse, 
    SearchRequest, 
    SearchResponse,
    ingest_document_tool,
    search_knowledge_tool
)


@pytest.fixture
def doc_id():
    """Generate a test document ID."""
    return uuid.uuid4()


@pytest.fixture
def valid_ingest_request():
    """Create a valid ingest request."""
    return IngestRequest(
        url="https://example.com/document",
        title="Test Document",
        source="test",
        metadata={"author": "Test Author", "category": "Test"}
    )


@pytest.fixture
def valid_search_request():
    """Create a valid search request."""
    return SearchRequest(
        query="test query",
        filters={"source": "test"},
        limit=10
    )


@pytest.fixture
def search_results():
    """Create sample search results."""
    return [
        {
            "id": "chunk1",
            "text": "This is the first search result",
            "metadata": {
                "title": "Document 1",
                "source": "test",
                "url": "https://example.com/doc1"
            },
            "score": 0.95
        },
        {
            "id": "chunk2",
            "text": "This is the second search result",
            "metadata": {
                "title": "Document 2",
                "source": "test",
                "url": "https://example.com/doc2"
            },
            "score": 0.85
        }
    ]


@pytest.fixture
def mock_mem0_client(search_results):
    """Mock Mem0 client for search operations."""
    client = AsyncMock()
    client.search.return_value = search_results
    return client


class TestMCPTools:
    """Test suite for MCP tools."""

    @pytest.mark.asyncio
    async def test_ingest_document_tool(self, valid_ingest_request):
        """Test the ingest_document MCP tool."""
        # Arrange
        job_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        
        # Mock the background tasks and UUID generation
        with patch("nexus_harvester.mcp.tools.uuid4", return_value=uuid.UUID(doc_id)), \
             patch("nexus_harvester.mcp.tools.process_and_index_document") as mock_process, \
             patch("nexus_harvester.mcp.tools.str", return_value=job_id):
            
            # Act
            response = await ingest_document_tool(valid_ingest_request)
            
            # Assert
            assert isinstance(response, IngestResponse)
            assert response.doc_id == doc_id
            assert response.job_id == job_id
            assert response.status == "accepted"
            
            # Verify process_and_index_document was called with correct arguments
            mock_process.assert_called_once()
            args, kwargs = mock_process.call_args
            assert kwargs["job_id"] == job_id
            assert isinstance(kwargs["doc_meta"], DocumentMeta)
            assert str(kwargs["doc_meta"].url) == valid_ingest_request.url
            assert kwargs["doc_meta"].title == valid_ingest_request.title
            assert kwargs["doc_meta"].source == valid_ingest_request.source
            assert kwargs["content"] == valid_ingest_request.content

    @pytest.mark.asyncio
    async def test_search_knowledge_tool(self, valid_search_request, search_results, mock_mem0_client):
        """Test the search_knowledge MCP tool."""
        # Arrange
        with patch("nexus_harvester.mcp.tools.get_mem0_client", return_value=mock_mem0_client):
            # Act
            response = await search_knowledge_tool(valid_search_request)
            
            # Assert
            assert isinstance(response, SearchResponse)
            assert response.query == valid_search_request.query
            assert response.count == len(search_results)
            assert response.results == search_results
            
            # Verify mem0_client.search was called with correct arguments
            mock_mem0_client.search.assert_called_once_with(
                query=valid_search_request.query,
                filters=valid_search_request.filters,
                limit=valid_search_request.limit
            )

    @pytest.mark.asyncio
    async def test_search_knowledge_tool_error(self, valid_search_request):
        """Test error handling in the search_knowledge MCP tool."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.search.side_effect = Exception("Search failed")
        
        with patch("nexus_harvester.mcp.tools.get_mem0_client", return_value=mock_client):
            # Act/Assert
            with pytest.raises(Exception, match="Search failed"):
                await search_knowledge_tool(valid_search_request)
