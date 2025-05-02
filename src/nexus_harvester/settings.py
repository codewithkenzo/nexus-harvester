"""Configuration settings for the Nexus Harvester."""

from typing import Optional
from pydantic import BaseSettings, HttpUrl, SecretStr


class KnowledgeHarvesterSettings(BaseSettings):
    """Application settings for the Nexus Harvester."""
    
    # Service configuration
    service_name: str = "nexus-harvester"
    host: str = "0.0.0.0"
    port: int = 8000
    mcp_port: int = 8001
    
    # Zep configuration
    zep_api_url: HttpUrl
    zep_api_key: SecretStr
    
    # Mem0 configuration
    mem0_api_url: HttpUrl
    mem0_api_key: SecretStr
    
    # Development only
    use_qdrant_dev: bool = False
    qdrant_url: Optional[HttpUrl] = None
    
    # Processing settings
    chunk_size: int = 512
    chunk_overlap: int = 128
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
