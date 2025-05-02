"""
Type Safety and Advanced Feature Test for Nexus Harvester Error Handling.

This module verifies:
1. Type safety of our error handling system
2. Proper request context preservation
3. Hierarchical error classification
4. Error recovery capabilities

Following Makima's strict protocol for absolute control and deterministic testing.
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC

import pytest
from pydantic import ValidationError as PydanticValidationError

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus_harvester.utils.errors import (
    NexusHarvesterError,
    InvalidRequestError, 
    ResourceNotFoundError,
    ValidationError,
    DependencyError,
    ErrorLocation,
    ErrorResponse,
    create_error_response,
    nexus_harvester_exception_handler
)

# ========== Fixtures ==========

@pytest.fixture
def test_request():
    """Create a mock request for testing."""
    return Request(scope={
        "type": "http",
        "path": "/test",
        "headers": [(b"x-request-id", b"test-req-id-123")],
        "method": "GET",
        "query_string": b"param=value",
        "client": ("127.0.0.1", 8000),
    })

# ========== Type Safety Tests ==========

@pytest.mark.parametrize("field_name,invalid_value,expected_error_type", [
    ("code", "not-a-number", "int_parsing"),  # Non-coercible string instead of int (Pydantic V2 error type)
    ("status", 123, "string_type"),   # Integer instead of string
    ("message", None, "string_type"), # None instead of string (note: not 'Field required' in Pydantic V2)
    ("error_type", 999, "string_type") # Integer instead of string
])
def test_error_response_field_validation(field_name, invalid_value, expected_error_type):
    """Test that ErrorResponse model enforces field type validation."""
    # Create valid base params
    params = {
        "code": 400,
        "message": "Test message",
        "error_type": "test_error"
    }
    
    # Override with invalid value for the specific field we're testing
    params[field_name] = invalid_value
    
    # This should raise ValidationError with expected error type
    with pytest.raises(PydanticValidationError) as exc:
        ErrorResponse(**params)
    
    # Verify error message contains expected error type
    error_detail = str(exc.value)
    assert expected_error_type in error_detail, f"Expected '{expected_error_type}' in error but got: {error_detail}"

def test_error_response_nested_validation():
    """Test that nested models in ErrorResponse are properly validated."""
    # Test with invalid nested location data
    with pytest.raises(PydanticValidationError) as exc:
        ErrorResponse(
            code=422,
            message="Validation error",
            error_type="validation_error",
            locations=[{"field": 123, "message": "Invalid field"}]  # Type error: int instead of str
        )
    
    error_detail = str(exc.value)
    assert "string_type" in error_detail, f"Expected string_type error but got: {error_detail}"
    
    # Test with valid nested location data works correctly
    valid_response = ErrorResponse(
        code=422,
        message="Validation error",
        error_type="validation_error",
        locations=[{"field": "username", "message": "Too short"}]
    )
    
    assert valid_response.locations[0].field == "username"

@pytest.mark.asyncio
async def test_error_handler_response_type(test_request):
    """Test that exception handlers return correct JSONResponse objects."""
    # Create different error types
    errors = [
        InvalidRequestError(message="Invalid parameter"),
        ResourceNotFoundError(message="Document not found"),
        ValidationError(message="Field validation failed"),
        DependencyError(message="Service unavailable")
    ]
    
    for error in errors:
        # Handler should return JSONResponse
        response = await nexus_harvester_exception_handler(test_request, error)
        
        # Type checks
        assert isinstance(response, JSONResponse), f"{error.__class__.__name__} handler didn't return JSONResponse"
        assert response.status_code == error.status_code, f"Status code mismatch for {error.__class__.__name__}"
        
        # Get response content
        content = json.loads(response.body.decode())
        
        # Structure validation
        required_fields = ["status", "code", "message", "error_type"]
        for field in required_fields:
            assert field in content, f"{error.__class__.__name__} response missing '{field}' field"
        
        # Type validation of response fields
        assert isinstance(content["status"], str)
        assert isinstance(content["code"], int)
        assert isinstance(content["message"], str)
        assert isinstance(content["error_type"], str)

def test_error_classification_hierarchy():
    """Test the error classification hierarchy and proper inheritance."""
    # Verify all error types inherit from base error
    error_classes = [
        InvalidRequestError,
        ResourceNotFoundError,
        ValidationError,
        DependencyError
    ]
    
    for error_class in error_classes:
        assert issubclass(error_class, NexusHarvesterError), \
               f"{error_class.__name__} should inherit from NexusHarvesterError"
    
    # Verify status code and type inheritance
    error_code_map = {
        NexusHarvesterError: 500,
        InvalidRequestError: 400, 
        ResourceNotFoundError: 404,
        ValidationError: 422,
        DependencyError: 503
    }
    
    for error_class, expected_code in error_code_map.items():
        error = error_class()
        assert error.status_code == expected_code, \
               f"{error_class.__name__} has incorrect status code {error.status_code}, expected {expected_code}"
        
        # Verify error_type exists and is a non-empty string
        assert isinstance(error.error_type, str), f"{error_class.__name__}.error_type should be a string"
        assert error.error_type, f"{error_class.__name__}.error_type should not be empty"

@pytest.mark.asyncio
async def test_context_preservation():
    """Test that errors preserve complete request context."""
    # Create request with rich context
    request_with_context = Request(scope={
        "type": "http",
        "path": "/documents/123/chunks",
        "headers": [
            (b"x-request-id", b"context-test-req-789"),
            (b"user-agent", b"pytest-client"),
            (b"content-type", b"application/json"),
        ],
        "method": "GET",
        "query_string": b"limit=50&offset=10",
        "client": ("192.168.1.10", 8000),
    })
    
    # Create error with detailed context
    error = ResourceNotFoundError(
        message="Document not found",
        details={
            "doc_id": "doc-789",
            "requested_at": datetime.now(UTC).isoformat(),
            "query_params": {"limit": 50, "offset": 10}
        }
    )
    
    # Get response
    response = await nexus_harvester_exception_handler(request_with_context, error)
    content = json.loads(response.body.decode())
    
    # Verify all context elements are preserved
    assert content["request_id"] == "context-test-req-789", "Request ID not preserved"
    assert content["details"]["doc_id"] == "doc-789", "Document ID not preserved"
    assert "requested_at" in content["details"], "Timestamp not preserved"
    assert content["details"]["query_params"]["limit"] == 50, "Query parameters not preserved correctly"

@pytest.mark.asyncio
@pytest.mark.parametrize("recoverable,retry_after,expected_status", [
    (True, 5, 503),       # Recoverable with retry hint
    (True, None, 503),    # Recoverable without retry hint
    (False, None, 503),   # Non-recoverable failure
])
async def test_error_recovery_capabilities(test_request, recoverable, retry_after, expected_status):
    """Test error recovery capabilities with different recovery scenarios."""
    # Configure recovery details
    details = {
        "service": "memory_store",
        "error": "Connection timeout",
        "recoverable": recoverable,
    }
    
    # Add retry_after if provided
    if retry_after is not None:
        details["retry_after"] = retry_after
    
    # Create dependency error with recovery details
    error = DependencyError(
        message="Service temporarily unavailable",
        details=details
    )
    
    # Get response
    response = await nexus_harvester_exception_handler(test_request, error)
    content = json.loads(response.body.decode())
    
    # Verify status code
    assert response.status_code == expected_status, f"Expected status {expected_status}, got {response.status_code}"
    
    # Verify recovery information is preserved correctly
    assert "details" in content, "Response missing details field"
    assert "recoverable" in content["details"], "Response missing recoverable flag"
    assert content["details"]["recoverable"] == recoverable, "Recoverable flag not correctly preserved"
    
    if retry_after is not None:
        assert "retry_after" in content["details"], "Retry_after field missing"
        assert content["details"]["retry_after"] == retry_after, "Retry_after value not preserved"

def test_traceback_handling_in_dev_mode(test_request):
    """Test that tracebacks are included in development mode but not in production."""
    # Create error with potential for complex traceback
    error = NexusHarvesterError(
        message="Complex internal error",
        details={"source": "processing_pipeline"}
    )
    
    # Create error response with traceback (dev mode)
    dev_response = create_error_response(test_request, error, include_traceback=True)
    
    # Verify traceback is included
    assert dev_response.traceback is not None, "Traceback should be included in dev mode"
    assert isinstance(dev_response.traceback, list), "Traceback should be a list of strings"
    assert len(dev_response.traceback) > 0, "Traceback should not be empty"
    
    # Create error response without traceback (production mode)
    prod_response = create_error_response(test_request, error, include_traceback=False)
    
    # Verify traceback is not included
    assert prod_response.traceback is None, "Traceback should not be included in production mode"

@pytest.mark.asyncio
async def test_custom_message_override(test_request):
    """Test that custom error messages properly override default messages."""
    # Create error with custom message
    custom_message = "This is a specific custom error message"
    error = ResourceNotFoundError(message=custom_message)
    
    # Get response
    response = await nexus_harvester_exception_handler(test_request, error)
    content = json.loads(response.body.decode())
    
    # Verify custom message is used
    assert content["message"] == custom_message, "Custom message not properly used"
    
    # Create error with default message
    default_error = ResourceNotFoundError()
    default_response = await nexus_harvester_exception_handler(test_request, default_error)
    default_content = json.loads(default_response.body.decode())
    
    # Verify default message is used
    assert default_content["message"] == "Resource not found", "Default message not properly used"
    
    # Verify they're different
    assert content["message"] != default_content["message"], "Custom and default messages should differ"
