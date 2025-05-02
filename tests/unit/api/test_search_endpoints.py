"""Unit tests for the search API endpoints."""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any, List, AsyncGenerator

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from httpx import AsyncClient

from nexus_harvester.api.search import router


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    app = FastAPI()
    app.include_router(router)
    return app


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


class TestSearchEndpoints:
    """Test suite for search endpoints."""

    def test_search_success(self, client, search_results, mock_mem0_client):
        """Test successful search operation."""
        # Arrange
        query = "test query"
        filters = {"source": "test"}
        limit = 10
        
        with patch("nexus_harvester.api.search.get_mem0_client", return_value=mock_mem0_client):
            # Act
            response = client.get(
                "/search",
                params={"query": query, "filters": json.dumps(filters), "limit": limit}
            )
            
            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["query"] == query
            assert response.json()["count"] == len(search_results)
            assert response.json()["results"] == search_results
            
            # Verify client call
            mock_mem0_client.search.assert_called_once_with(
                query=query,
                filters=filters,
                limit=limit
            )

    def test_search_missing_query(self, client):
        """Test search with missing query parameter."""
        # Act
        response = client.get("/search")
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "query" in response.json()["detail"][0]["loc"]

    def test_search_invalid_limit(self, client):
        """Test search with invalid limit parameter."""
        # Act
        response = client.get("/search", params={"query": "test", "limit": 100})
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "limit" in response.json()["detail"][0]["loc"]

    def test_search_invalid_filters_format(self, client):
        """Test search with invalid filters format."""
        # Act
        response = client.get(
            "/search",
            params={"query": "test", "filters": "invalid-json"}
        )
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "filters" in response.json()["detail"][0]["loc"]

    def test_search_client_error(self, client):
        """Test search with client error."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.search.side_effect = Exception("Search failed")
        
        with patch("nexus_harvester.api.search.get_mem0_client", return_value=mock_client):
            # Act
            response = client.get("/search", params={"query": "test"})
            
            # Assert
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Search failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_stream_search(self, async_client, search_results, mock_mem0_client):
        """Test streaming search results."""
        # Arrange
        query = "test query"
        
        # Mock the event generator
        async def mock_event_generator():
            yield f"data: {json.dumps({'status': 'processing'})}\n\n"
            for result in search_results:
                yield f"data: {json.dumps(result)}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'status': 'complete', 'total': len(search_results)})}\n\n"
        
        with patch("nexus_harvester.api.search.get_mem0_client", return_value=mock_mem0_client), \
             patch("nexus_harvester.api.search.event_generator", return_value=mock_event_generator()):
            
            # Act
            response = await async_client.get(
                "/search/stream",
                params={"query": query}
            )
            
            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/event-stream"
            assert "cache-control" in response.headers
            assert "connection" in response.headers

    @pytest.mark.asyncio
    async def test_stream_search_error(self, async_client):
        """Test streaming search with error."""
        # Arrange
        query = "test query"
        
        # Mock client to raise an exception
        mock_client = AsyncMock()
        mock_client.search.side_effect = Exception("Search failed")
        
        # Mock the event generator to include an error
        async def mock_event_generator():
            yield f"data: {json.dumps({'status': 'processing'})}\n\n"
            yield f"data: {json.dumps({'status': 'error', 'message': 'Search failed'})}\n\n"
        
        with patch("nexus_harvester.api.search.get_mem0_client", return_value=mock_client), \
             patch("nexus_harvester.api.search.event_generator", return_value=mock_event_generator()):
            
            # Act
            response = await async_client.get(
                "/search/stream",
                params={"query": query}
            )
            
            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/event-stream"
