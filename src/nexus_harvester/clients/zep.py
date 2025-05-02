"""Client for Zep memory operations."""

from typing import List, Dict, Any
import httpx
from pydantic import SecretStr

from nexus_harvester.models import Chunk


class ZepClient:
    """Client for Zep memory operations."""
    def __init__(self, api_url: str, api_key: SecretStr):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers)
    
    async def store_memory(self, session_id: str, chunks: List[Chunk], 
                          metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Store chunks in Zep memory."""
        payload = {
            "session_id": session_id,
            "chunks": [chunk.model_dump() for chunk in chunks],
            "metadata": metadata or {}
        }
        response = await self.client.post(
            f"{self.api_url}/memory",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def get_memory(self, session_id: str, 
                         limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve memory for a session."""
        response = await self.client.get(
            f"{self.api_url}/memory/{session_id}",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
