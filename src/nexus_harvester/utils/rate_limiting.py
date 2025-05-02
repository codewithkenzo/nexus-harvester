"""
Token bucket rate limiting implementation for Nexus Harvester.

This module implements a thread-safe token bucket algorithm for rate limiting
API requests with strict typing and high-performance characteristics.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Protocol, cast

import structlog
from pydantic import Field, BaseModel, ConfigDict, field_validator

from nexus_harvester.utils.errors import NexusHarvesterError


# Set up logger with proper context
logger = structlog.get_logger(__name__)


class RateLimitError(NexusHarvesterError):
    """Exception raised when a client exceeds their rate limit."""
    
    def __init__(
        self, 
        message: str = "Rate limit exceeded",
        retry_after: float = 1.0, 
        client_id: str = "unknown"
    ):
        """Initialize rate limit error with retry information.
        
        Args:
            message: Error message
            retry_after: Seconds the client should wait before retrying
            client_id: Identifier for the client that was rate limited
        """
        self.retry_after = retry_after
        self.client_id = client_id
        super().__init__(message)


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting with strict validation."""
    
    tokens_per_second: float = Field(gt=0, le=1000, default=10.0)
    bucket_size: int = Field(gt=0, le=10000, default=20)
    
    # Modern Pydantic V2 config
    model_config = ConfigDict(
        frozen=True,
        extra="forbid"
    )
    
    @field_validator("tokens_per_second")
    @classmethod
    def validate_tokens_per_second(cls, v: float) -> float:
        """Validate that tokens per second is a reasonable rate."""
        if v <= 0:
            raise ValueError("Tokens per second must be positive")
        return v
    
    @field_validator("bucket_size")
    @classmethod
    def validate_bucket_size(cls, v: int) -> int:
        """Validate that bucket size is reasonable."""
        if v <= 0:
            raise ValueError("Bucket size must be positive")
        return v


class TokenBucket:
    """Thread-safe token bucket implementation for rate limiting."""
    
    def __init__(self, rate: float, capacity: int):
        """Initialize a token bucket with a given rate and capacity.
        
        Args:
            rate: Token refill rate in tokens per second
            capacity: Maximum token capacity (bucket size)
        """
        self._rate: float = rate
        self._capacity: int = capacity
        self._tokens: float = float(capacity)
        self._last_refill: float = time.monotonic()
        self._lock = threading.RLock()
    
    def _refill(self) -> None:
        """Refill the token bucket based on elapsed time."""
        now = time.monotonic()
        delta = now - self._last_refill
        self._tokens = min(
            self._capacity, 
            self._tokens + (delta * self._rate)
        )
        self._last_refill = now
    
    def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            Tuple containing:
                - Whether tokens were successfully consumed
                - Time in seconds to wait for sufficient tokens if unsuccessful
        """
        if tokens <= 0:
            raise ValueError("Token count must be positive")
            
        with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True, 0.0
            
            # Calculate wait time for sufficient tokens
            additional_tokens_needed = tokens - self._tokens
            wait_time = additional_tokens_needed / self._rate
            
            return False, wait_time
    
    @property
    def tokens(self) -> float:
        """Get current token count (thread-safe).
        
        Returns:
            Current number of tokens in the bucket
        """
        with self._lock:
            self._refill()
            return self._tokens


class RateLimiter:
    """Rate limiter using token buckets with client tracking capabilities."""
    
    def __init__(self, config: RateLimitConfig):
        """Initialize rate limiter with configuration.
        
        Args:
            config: Rate limiter configuration
        """
        self._config = config
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.RLock()
    
    def _get_bucket(self, client_id: str) -> TokenBucket:
        """Get or create a token bucket for a client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Token bucket for the client
        """
        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = TokenBucket(
                    rate=self._config.tokens_per_second,
                    capacity=self._config.bucket_size
                )
            return self._buckets[client_id]
    
    def check_rate_limit(self, client_id: str, tokens: int = 1) -> None:
        """Check if a client has exceeded their rate limit.
        
        Args:
            client_id: Client identifier (IP, API key, etc.)
            tokens: Number of tokens to consume
            
        Raises:
            RateLimitError: If the client has exceeded their rate limit
        """
        bucket = self._get_bucket(client_id)
        allowed, wait_time = bucket.consume(tokens)
        
        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                wait_time=wait_time,
                requested_tokens=tokens
            )
            raise RateLimitError(
                message=f"Rate limit exceeded. Try again in {wait_time:.2f} seconds.",
                retry_after=wait_time,
                client_id=client_id
            )
    
    def reset(self, client_id: Optional[str] = None) -> None:
        """Reset rate limiting for a client or all clients.
        
        Args:
            client_id: Client to reset, or None to reset all clients
        """
        with self._lock:
            if client_id is None:
                self._buckets.clear()
            elif client_id in self._buckets:
                del self._buckets[client_id]
