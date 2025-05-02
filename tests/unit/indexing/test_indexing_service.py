"""Unit tests for the IndexingService component."""

import asyncio
import uuid
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from pydantic import SecretStr

from nexus_harvester.models import Chunk, DocumentMeta
from nexus_harvester.clients.zep import ZepClient
from nexus_harvester.clients.mem0 import Mem0Client
from nexus_harvester.indexing.indexing_service import IndexingService, IndexingResult


@pytest.fixture
def doc_id():
    """Generate a test document ID."""
    return uuid.uuid4()


@pytest.fixture
def test_chunks(doc_id):
    """Generate test chunks for a document."""
    return [
        Chunk(
            doc_id=doc_id,
            text=f"Test chunk {i}",
            index=i,
            metadata={"title": "Test Document", "source": "test", "url": "https://example.com"}
        )
        for i in range(3)
    ]


@pytest.fixture
def mock_zep_client():
    """Create a mock ZepClient."""
    client = AsyncMock(spec=ZepClient)
    client.store_memory.return_value = {"status": "success", "count": 3}
    return client


@pytest.fixture
def mock_mem0_client():
    """Create a mock Mem0Client."""
    client = AsyncMock(spec=Mem0Client)
    client.index_chunks.return_value = {"status": "indexed", "count": 3}
    return client


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = MagicMock()
    client.index_chunks = AsyncMock(return_value={"status": "indexed", "count": 3})
    return client


class TestIndexingService:
    """Test suite for the IndexingService component."""

    @pytest.mark.asyncio
    async def test_index_chunks_success(self, doc_id, test_chunks, mock_zep_client, mock_mem0_client):
        """Test successful indexing of chunks to all backends."""
        # Arrange
        service = IndexingService(
            zep_client=mock_zep_client,
            mem0_client=mock_mem0_client,
            use_qdrant_dev=False
        )
        
        # Act
        result = await service.index_chunks(doc_id, test_chunks)
        
        # Assert
        assert result.doc_id == doc_id  # Now comparing UUID objects directly
        assert result.chunk_count == len(test_chunks)
        assert "zep" in result.backends
        assert "mem0" in result.backends
        assert result.backends["zep"]["status"] == "success"
        assert result.backends["mem0"]["status"] == "indexed"
        
        # Verify client calls
        mock_zep_client.store_memory.assert_called_once()
        mock_mem0_client.index_chunks.assert_called_once_with(test_chunks)

    @pytest.mark.asyncio
    async def test_index_chunks_with_session_id(self, doc_id, test_chunks, mock_zep_client, mock_mem0_client):
        """Test indexing with a custom session ID."""
        # Arrange
        service = IndexingService(
            zep_client=mock_zep_client,
            mem0_client=mock_mem0_client,
            use_qdrant_dev=False
        )
        session_id = "custom-session-123"
        
        # Act
        result = await service.index_chunks(doc_id, test_chunks, session_id=session_id)
        
        # Assert
        assert result.doc_id == doc_id  # Now comparing UUID objects directly
        
        # Verify session ID was used
        mock_zep_client.store_memory.assert_called_once_with(
            session_id, test_chunks, None
        )

    @pytest.mark.asyncio
    async def test_index_chunks_with_qdrant_dev(
        self, doc_id, test_chunks, mock_zep_client, mock_mem0_client, mock_qdrant_client
    ):
        """Test indexing with Qdrant in development mode."""
        # Arrange
        service = IndexingService(
            zep_client=mock_zep_client,
            mem0_client=mock_mem0_client,
            qdrant_client=mock_qdrant_client,
            use_qdrant_dev=True
        )
        
        # Act
        result = await service.index_chunks(doc_id, test_chunks)
        
        # Assert
        assert "qdrant" in result.backends
        assert result.backends["qdrant"]["status"] == "indexed"
        
        # Verify Qdrant client was called
        mock_qdrant_client.index_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_chunks_without_qdrant_client(
        self, doc_id, test_chunks, mock_zep_client, mock_mem0_client
    ):
        """Test indexing with Qdrant enabled but no client provided."""
        # Arrange
        service = IndexingService(
            zep_client=mock_zep_client,
            mem0_client=mock_mem0_client,
            qdrant_client=None,
            use_qdrant_dev=True
        )
        
        # Act
        result = await service.index_chunks(doc_id, test_chunks)
        
        # Assert
        assert "qdrant" in result.backends
        assert result.backends["qdrant"]["status"] == "skipped"
        assert "No Qdrant client configured" in result.backends["qdrant"]["reason"]

    @pytest.mark.asyncio
    async def test_index_chunks_error_handling(self, doc_id, test_chunks, mock_zep_client, mock_mem0_client):
        """Test error handling during indexing."""
        # Arrange
        mock_zep_client.store_memory.side_effect = Exception("Zep connection error")
        
        service = IndexingService(
            zep_client=mock_zep_client,
            mem0_client=mock_mem0_client,
            use_qdrant_dev=False
        )
        
        # Act
        result = await service.index_chunks(doc_id, test_chunks)
        
        # Assert
        assert result.doc_id == doc_id  # Now comparing UUID objects directly
        assert "error" in result.backends["zep"]
        assert "Zep connection error" in result.backends["zep"]["error"]
        
        # Mem0 should still be called even if Zep fails
        mock_mem0_client.index_chunks.assert_called_once_with(test_chunks)
