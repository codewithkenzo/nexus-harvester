"""Configuration settings for the Nexus Harvester."""

from typing import Optional, Dict, List
from pydantic import HttpUrl, SecretStr, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class RateLimitSettings(BaseSettings):
    """Rate limiting settings with strict validation."""
    
    enabled: bool = True
    tokens_per_second: float = Field(default=10.0, gt=0, le=1000)
    bucket_size: int = Field(default=20, gt=0, le=10000)
    excluded_paths: List[str] = Field(default_factory=lambda: ["/docs", "/redoc", "/openapi.json"])
    
    # Modern ConfigDict approach
    model_config = ConfigDict(
        frozen=True,
        extra="forbid"
    )
    
    @field_validator("tokens_per_second")
    @classmethod
    def validate_tokens_per_second(cls, v: float) -> float:
        """Validate tokens per second is reasonable."""
        if v <= 0:
            raise ValueError("Tokens per second must be positive")
        if v > 1000:
            raise ValueError("Tokens per second must be at most 1000")
        return v


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
    max_chunks_per_doc: int = 1000
    
    # Rate limiting settings
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    
    # Modern ConfigDict approach instead of class-based Config
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True
    )
    
    def get_rate_limit_config(self) -> Dict:
        """Get rate limit configuration as a dictionary.
        
        Returns:
            Dict containing rate limit configuration values
        """
        return self.rate_limit.model_dump()
