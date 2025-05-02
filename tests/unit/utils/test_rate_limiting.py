"""
Tests for rate limiting implementation.

Comprehensive test suite for token bucket and rate limiting components
with precise time control and edge case validation.
"""
from __future__ import annotations

import asyncio
import time
from unittest import mock

import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus_harvester.utils.rate_limiting import (
    RateLimitConfig, 
    RateLimitError,
    RateLimiter, 
    TokenBucket
)
from nexus_harvester.middleware.rate_limiting import (
    RateLimitMiddleware,
    add_rate_limiting,
    _get_client_identifier
)


class TestTokenBucket:
    """Test cases for the TokenBucket implementation."""
    
    def test_initial_state(self):
        """Test initial state of token bucket."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        assert bucket.tokens == 20
        
    def test_consume_success(self):
        """Test successful token consumption."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        allowed, wait_time = bucket.consume(5)
        
        assert allowed is True
        assert wait_time == 0.0
        assert abs(bucket.tokens - 15) < 0.01  # Allow small floating-point precision errors
    
    def test_consume_too_many(self):
        """Test consuming more tokens than available."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        allowed, wait_time = bucket.consume(25)
        
        assert allowed is False
        assert wait_time > 0.0
        assert bucket.tokens == 20  # Tokens unchanged on failure
    
    def test_refill(self):
        """Test token refill based on elapsed time."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        
        # Consume some tokens
        bucket.consume(15)
        assert abs(bucket.tokens - 5) < 0.01  # Allow small floating-point precision errors
        
        # Mock time advancement (0.5 seconds = 5 tokens at rate=10)
        with mock.patch('time.monotonic', return_value=time.monotonic() + 0.5):
            # Verify tokens refilled
            assert abs(bucket.tokens - 10) < 0.01  # Allow small floating-point precision errors
    
    def test_refill_max_capacity(self):
        """Test refill respects maximum capacity."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        
        # Mock time advancement (10 seconds = 100 tokens at rate=10)
        with mock.patch('time.monotonic', return_value=time.monotonic() + 10):
            # Verify tokens capped at capacity
            assert bucket.tokens == 20
    
    def test_invalid_token_request(self):
        """Test consuming an invalid number of tokens."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        
        with pytest.raises(ValueError):
            bucket.consume(0)
            
        with pytest.raises(ValueError):
            bucket.consume(-1)


class TestRateLimitConfig:
    """Test cases for rate limit configuration validation."""
    
    def test_valid_config(self):
        """Test valid rate limit configuration."""
        config = RateLimitConfig(tokens_per_second=15.5, bucket_size=30)
        assert config.tokens_per_second == 15.5
        assert config.bucket_size == 30
    
    def test_invalid_tokens_per_second(self):
        """Test invalid tokens per second validation."""
        with pytest.raises(ValidationError):
            RateLimitConfig(tokens_per_second=0)
            
        with pytest.raises(ValidationError):
            RateLimitConfig(tokens_per_second=-5.0)
            
        with pytest.raises(ValidationError):
            RateLimitConfig(tokens_per_second=1001)  # Beyond max
    
    def test_invalid_bucket_size(self):
        """Test invalid bucket size validation."""
        with pytest.raises(ValidationError):
            RateLimitConfig(bucket_size=0)
            
        with pytest.raises(ValidationError):
            RateLimitConfig(bucket_size=-10)
            
        with pytest.raises(ValidationError):
            RateLimitConfig(bucket_size=10001)  # Beyond max
    
    def test_default_values(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        assert config.tokens_per_second == 10.0
        assert config.bucket_size == 20


class TestRateLimiter:
    """Test cases for the RateLimiter implementation."""
    
    def test_check_rate_limit_success(self):
        """Test successful rate limit check."""
        config = RateLimitConfig(tokens_per_second=10, bucket_size=10)
        limiter = RateLimiter(config=config)
        
        # Should not raise an exception
        limiter.check_rate_limit("test_client", tokens=5)
        
        # Check again with remaining tokens
        limiter.check_rate_limit("test_client", tokens=3)
    
    def test_check_rate_limit_exceeded(self):
        """Test rate limit exceeded with appropriate error."""
        config = RateLimitConfig(tokens_per_second=10, bucket_size=10)
        limiter = RateLimiter(config=config)
        
        # First request succeeds
        limiter.check_rate_limit("test_client", tokens=6)
        
        # Second request exceeds limit
        with pytest.raises(RateLimitError) as exc_info:
            limiter.check_rate_limit("test_client", tokens=5)
        
        # Verify error details
        assert "Rate limit exceeded" in str(exc_info.value)
        assert exc_info.value.client_id == "test_client"
        assert exc_info.value.retry_after > 0
    
    def test_different_clients(self):
        """Test rate limiting for different clients."""
        config = RateLimitConfig(tokens_per_second=10, bucket_size=5)
        limiter = RateLimiter(config=config)
        
        # Client 1 consumes tokens
        limiter.check_rate_limit("client1", tokens=4)
        
        # Client 2 should have full tokens
        limiter.check_rate_limit("client2", tokens=5)
        
        # Client 1 should be rate limited
        with pytest.raises(RateLimitError):
            limiter.check_rate_limit("client1", tokens=2)
    
    def test_reset_single_client(self):
        """Test resetting a single client."""
        config = RateLimitConfig(tokens_per_second=10, bucket_size=5)
        limiter = RateLimiter(config=config)
        
        # Consume some tokens
        limiter.check_rate_limit("client1", tokens=4)
        limiter.check_rate_limit("client2", tokens=3)
        
        # Reset client1
        limiter.reset("client1")
        
        # client1 should have full tokens again
        limiter.check_rate_limit("client1", tokens=5)
        
        # client2 should still be limited
        with pytest.raises(RateLimitError):
            limiter.check_rate_limit("client2", tokens=3)
    
    def test_reset_all_clients(self):
        """Test resetting all clients."""
        config = RateLimitConfig(tokens_per_second=10, bucket_size=5)
        limiter = RateLimiter(config=config)
        
        # Consume tokens for multiple clients
        limiter.check_rate_limit("client1", tokens=4)
        limiter.check_rate_limit("client2", tokens=4)
        
        # Reset all clients
        limiter.reset()
        
        # Both clients should have full tokens
        limiter.check_rate_limit("client1", tokens=5)
        limiter.check_rate_limit("client2", tokens=5)


def create_test_app() -> FastAPI:
    """Create a test FastAPI app with rate limiting."""
    app = FastAPI()
    
    config = RateLimitConfig(tokens_per_second=5, bucket_size=5)
    add_rate_limiting(app, config=config)
    
    @app.get("/test")
    async def test_endpoint():
        return {"status": "success"}
    
    @app.get("/excluded")
    async def excluded_endpoint():
        return {"status": "success"}
    
    return app


class TestRateLimitingMiddleware:
    """Test cases for rate limiting middleware."""
    
    def test_middleware_allows_requests_under_limit(self):
        """Test middleware allows requests under the rate limit."""
        app = create_test_app()
        client = TestClient(app)
        
        # Make requests under the limit
        for _ in range(5):
            response = client.get("/test")
            assert response.status_code == 200
            assert "X-RateLimit-Remaining" in response.headers
    
    def test_middleware_blocks_requests_over_limit(self):
        """Test middleware blocks requests over the rate limit."""
        app = create_test_app()
        client = TestClient(app)
        
        # Use up the limit
        for _ in range(5):
            client.get("/test")
        
        # Next request should be rate limited
        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"
    
    def test_rate_limit_headers(self):
        """Test rate limit headers in responses."""
        app = create_test_app()
        client = TestClient(app)
        
        # First request should have maximum tokens remaining
        response = client.get("/test")
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"
        
        # Second request should have one less token
        response = client.get("/test")
        assert response.headers["X-RateLimit-Remaining"] == "3"
    
    def test_excluded_paths(self):
        """Test excluded paths bypass rate limiting."""
        app = FastAPI()
        
        config = RateLimitConfig(tokens_per_second=5, bucket_size=5)
        add_rate_limiting(app, config=config, exclude_paths=["/excluded"])
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "success"}
        
        @app.get("/excluded")
        async def excluded_endpoint():
            return {"status": "success"}
        
        client = TestClient(app)
        
        # Use up the limit on rate-limited endpoint
        for _ in range(5):
            client.get("/test")
        
        # Next request to rate-limited endpoint should be blocked
        response = client.get("/test")
        assert response.status_code == 429
        
        # Excluded endpoint should still work
        response = client.get("/excluded")
        assert response.status_code == 200


class TestClientIdentification:
    """Test client identification from requests."""
    
    def test_api_key_header(self):
        """Test extraction of API key from header."""
        mock_request = mock.MagicMock()
        mock_request.headers = {"X-API-Key": "test_key"}
        mock_request.query_params = {}
        
        client_id = _get_client_identifier(mock_request)
        assert client_id == "api_key:test_key"
    
    def test_api_key_query(self):
        """Test extraction of API key from query parameter."""
        mock_request = mock.MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {"api_key": "test_key"}
        
        client_id = _get_client_identifier(mock_request)
        assert client_id == "api_key:test_key"
    
    def test_forwarded_ip(self):
        """Test extraction of forwarded IP address."""
        mock_request = mock.MagicMock()
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        mock_request.query_params = {}
        
        client_id = _get_client_identifier(mock_request)
        assert client_id == "ip:192.168.1.1"
    
    def test_direct_client_ip(self):
        """Test extraction of direct client IP address."""
        mock_request = mock.MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.client.host = "192.168.1.2"
        
        client_id = _get_client_identifier(mock_request)
        assert client_id == "ip:192.168.1.2"
