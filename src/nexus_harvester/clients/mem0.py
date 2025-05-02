"""Client for Mem0 search operations."""

from typing import List, Dict, Any
import httpx
from pydantic import SecretStr

from nexus_harvester.models import Chunk


class Mem0Client:
    """Client for Mem0 search operations."""
    def __init__(self, api_url: str, api_key: SecretStr):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers)
    
    async def index_chunks(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """Index chunks in Mem0."""
        payload = {
            "chunks": [chunk.model_dump() for chunk in chunks]
        }
        response = await self.client.post(
            f"{self.api_url}/index",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def search(self, query: str, filters: Dict[str, Any] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
        """Search indexed chunks."""
        payload = {
            "query": query,
            "filters": filters or {},
            "limit": limit
        }
        response = await self.client.post(
            f"{self.api_url}/search",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
