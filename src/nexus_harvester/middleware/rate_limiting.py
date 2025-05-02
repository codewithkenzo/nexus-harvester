"""
Rate limiting middleware for FastAPI in Nexus Harvester.

Implements a high-performance, type-safe middleware for enforcing
rate limits on API endpoints with proper error handling and headers.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, Optional, cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from nexus_harvester.utils.rate_limiting import RateLimiter, RateLimitConfig, RateLimitError
from nexus_harvester.utils.rate_limiting_errors import create_rate_limit_response


# Set up logger with proper context
logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for enforcing rate limits on API requests."""
    
    def __init__(
        self, 
        app: ASGIApp, 
        rate_limiter: RateLimiter,
        exclude_paths: Optional[list[str]] = None,
    ):
        """Initialize rate limiting middleware.
        
        Args:
            app: The ASGI application
            rate_limiter: Rate limiter instance to use
            exclude_paths: List of path prefixes to exclude from rate limiting
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.exclude_paths = exclude_paths or []
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process a request through rate limiting middleware.
        
        Args:
            request: The incoming request
            call_next: The next middleware or endpoint in the chain
            
        Returns:
            The response, potentially a rate limit error response
        """
        # Skip rate limiting for excluded paths
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)
        
        # Get client identifier (IP address or API key if available)
        client_id = _get_client_identifier(request)
        
        try:
            # Check rate limit before processing the request
            self.rate_limiter.check_rate_limit(client_id)
            
            # Process the request if rate limit not exceeded
            response = await call_next(request)
            
            # Add rate limit headers to the response
            remaining_tokens = self.rate_limiter._get_bucket(client_id).tokens
            response.headers["X-RateLimit-Remaining"] = str(int(remaining_tokens))
            response.headers["X-RateLimit-Limit"] = str(
                self.rate_limiter._config.bucket_size
            )
            
            return response
            
        except RateLimitError as e:
            # Create a standardized error response for rate limit errors
            error_response = create_rate_limit_response(
                error_type="rate_limit_exceeded",
                message=str(e),
                detail={
                    "retry_after": e.retry_after,
                    "client_id": e.client_id
                }
            )
            
            # Convert to JSONResponse with appropriate headers
            response = JSONResponse(
                status_code=429,
                content=error_response.model_dump()
            )
            
            # Add rate limit headers
            response.headers["Retry-After"] = str(int(e.retry_after))
            response.headers["X-RateLimit-Limit"] = str(
                self.rate_limiter._config.bucket_size
            )
            response.headers["X-RateLimit-Remaining"] = "0"
            
            return response


def _get_client_identifier(request: Request) -> str:
    """Extract a client identifier from a request.
    
    Attempts to use API key if present, falls back to client IP address.
    
    Args:
        request: The incoming request
        
    Returns:
        A unique identifier for the client
    """
    # First check for API key in header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key}"
    
    # Then check for API key in query parameters
    api_key_query = request.query_params.get("api_key")
    if api_key_query:
        return f"api_key:{api_key_query}"
    
    # Fall back to client IP (with forwarded IP support)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Get the first IP in the chain (client IP)
        client_ip = forwarded_for.split(",")[0].strip()
        return f"ip:{client_ip}"
    
    # Use direct client IP as last resort
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def add_rate_limiting(
    app: FastAPI, 
    config: Optional[RateLimitConfig] = None,
    exclude_paths: Optional[list[str]] = None
) -> None:
    """Add rate limiting middleware to a FastAPI application.
    
    Args:
        app: FastAPI application instance
        config: Rate limiting configuration (or use default)
        exclude_paths: List of path prefixes to exclude from rate limiting
    """
    # Use provided config or create default
    rate_config = config or RateLimitConfig()
    
    # Create rate limiter
    rate_limiter = RateLimiter(config=rate_config)
    
    # Add middleware to app
    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=rate_limiter,
        exclude_paths=exclude_paths or ["/docs", "/redoc", "/openapi.json"],
    )
    
    # Register exception handler for direct handling of RateLimitError
    @app.exception_handler(RateLimitError)
    async def rate_limit_exception_handler(
        request: Request, exc: RateLimitError
    ) -> JSONResponse:
        """Handle rate limit exceptions raised directly in endpoints.
        
        Args:
            request: The request that triggered the exception
            exc: The rate limit exception
            
        Returns:
            A properly formatted JSON response with appropriate headers
        """
        error_response = create_rate_limit_response(
            error_type="rate_limit_exceeded",
            message=str(exc),
            detail={
                "retry_after": exc.retry_after,
                "client_id": exc.client_id
            }
        )
        
        response = JSONResponse(
            status_code=429,
            content=error_response.model_dump()
        )
        
        response.headers["Retry-After"] = str(int(exc.retry_after))
        return response
    
    logger.info(
        "Rate limiting middleware configured",
        tokens_per_second=rate_config.tokens_per_second,
        bucket_size=rate_config.bucket_size,
        excluded_paths=exclude_paths
    )
