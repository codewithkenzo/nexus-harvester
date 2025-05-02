"""Standardized error handling for Nexus Harvester.

This module provides:
1. Custom exception classes for different error types
2. Standardized error response models
3. Exception handlers to register with FastAPI
4. Integration with structured logging
"""

import traceback
from typing import Any, Dict, List, Optional, Type, Union, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus_harvester.utils.logging import get_logger

# Set up logging
logger = get_logger(__name__)


# --- Error Response Models ---

class ErrorLocation(BaseModel):
    """Location of an error (field name, query param, etc.)."""
    
    field: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized error response model."""
    
    status: str = "error"
    code: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Human-readable error message")
    error_type: str = Field(..., description="Error classification")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    locations: Optional[List[ErrorLocation]] = Field(None, description="Error locations (for validation errors)")
    traceback: Optional[List[str]] = Field(None, description="Stack trace (only in development)")


# --- Custom Exception Classes ---

class NexusHarvesterError(Exception):
    """Base exception for all Nexus Harvester errors."""
    
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "server_error"
    message: str = "An unexpected error occurred"
    
    def __init__(
        self, 
        message: Optional[str] = None, 
        details: Optional[Dict[str, Any]] = None,
        locations: Optional[List[ErrorLocation]] = None
    ):
        self.message = message or self.message
        self.details = details
        self.locations = locations
        super().__init__(self.message)


class ValidationError(NexusHarvesterError):
    """Validation error for invalid input."""
    
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "validation_error"
    message = "Invalid input data"


class ResourceNotFoundError(NexusHarvesterError):
    """Resource not found error."""
    
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not_found"
    message = "Resource not found"


class InvalidRequestError(NexusHarvesterError):
    """Invalid request error."""
    
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "invalid_request"
    message = "Invalid request"


class AuthenticationError(NexusHarvesterError):
    """Authentication error."""
    
    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "authentication_error"
    message = "Authentication failed"


class AuthorizationError(NexusHarvesterError):
    """Authorization error."""
    
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "authorization_error"
    message = "Not authorized to access this resource"


class DependencyError(NexusHarvesterError):
    """External dependency error."""
    
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_type = "dependency_error"
    message = "External service dependency failed"


class RateLimitError(NexusHarvesterError):
    """Rate limit exceeded error."""
    
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limit_error"
    message = "Rate limit exceeded"


# --- Exception Handlers ---

def create_error_response(
    request: Request, 
    exc: NexusHarvesterError, 
    include_traceback: bool = False
) -> ErrorResponse:
    """Create standardized error response from exception."""
    # Get request ID from header or context
    request_id = request.headers.get("X-Request-ID", None)
    
    # Get traceback for development environments
    tb = None
    if include_traceback:
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    
    # Build error response
    return ErrorResponse(
        code=exc.status_code,
        message=exc.message,
        error_type=exc.error_type,
        request_id=request_id,
        details=exc.details,
        locations=exc.locations,
        traceback=tb
    )


async def nexus_harvester_exception_handler(
    request: Request, 
    exc: NexusHarvesterError
) -> JSONResponse:
    """Handle custom Nexus Harvester exceptions.
    
    Compatible with FastAPI exception handler type requirements.
    """
    # Get environment from settings (later can be injected)
    # For now hardcoded to development
    is_dev = True
    
    # Log the error with context
    log_context = {
        "error_type": exc.error_type,
        "status_code": exc.status_code,
        "path": request.url.path,
        "method": request.method,
    }
    
    if exc.details:
        log_context["details"] = exc.details
    
    logger.error(
        f"Request error: {exc.message}", 
        **log_context,
        exc_info=is_dev
    )
    
    # Create error response
    error_response = create_error_response(
        request=request,
        exc=exc,
        include_traceback=is_dev
    )
    
    # Return JSON response
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True)
    )


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Special handler for validation errors with field information."""
    return await nexus_harvester_exception_handler(request, exc)


# --- Exception Registration ---

def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with FastAPI application."""
    # Register handlers for custom exceptions - with type cast for mypy compatibility
    from typing import cast, Callable, Awaitable
    from fastapi.types import Exc, ExcHandlerFunc
    
    # Type cast our handlers to make FastAPI/mypy happy
    nexus_handler = cast(ExcHandlerFunc, nexus_harvester_exception_handler)
    validation_handler = cast(ExcHandlerFunc, validation_exception_handler)
    
    # Register our handlers with the app
    app.add_exception_handler(NexusHarvesterError, nexus_handler)
    app.add_exception_handler(ValidationError, validation_handler)
    
    # Register handler for FastAPI's RequestValidationError
    # This converts FastAPI's validation errors to our custom format
    @app.exception_handler(status.HTTP_422_UNPROCESSABLE_ENTITY)
    async def fastapi_validation_exception_handler(request: Request, exc: Any) -> JSONResponse:
        # Convert FastAPI validation error format to our format
        locations = []
        for error in getattr(exc, "errors", []):
            field = ".".join(str(loc) for loc in error.get("loc", []))
            message = error.get("msg", "Validation error")
            locations.append(ErrorLocation(field=field, message=message))
        
        # Create custom exception
        custom_exc = ValidationError(
            message="Request validation failed",
            locations=locations
        )
        
        # Use the standard handler
        return await nexus_harvester_exception_handler(request, custom_exc)
    
    # Generic exception handler for unexpected errors
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Convert to custom exception
        custom_exc = NexusHarvesterError(
            message=f"Unexpected error: {str(exc)}",
            details={"error_class": exc.__class__.__name__}
        )
        
        # Use the standard handler
        return await nexus_harvester_exception_handler(request, custom_exc)
