"""
Focused verification of Nexus Harvester error handling implementation.

This module validates that error classes and handlers produce correct responses
without requiring the full API stack.
"""

import json
import asyncio
from typing import Dict, Any, List, Optional

import pytest
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from nexus_harvester.utils.errors import (
    NexusHarvesterError,
    InvalidRequestError, 
    ResourceNotFoundError,
    ValidationError,
    DependencyError,
    nexus_harvester_exception_handler
)

# Define test fixtures

@pytest.fixture
def test_request():
    """Create a minimal Request object for testing."""
    app = FastAPI()
    scope = {
        "type": "http",
        "path": "/test",
        "headers": [(b"x-request-id", b"test-123")],
        "method": "GET",
    }
    return Request(scope)

@pytest.fixture
def test_errors() -> Dict[str, NexusHarvesterError]:
    """Create error instances for testing."""
    return {
        "InvalidRequestError": InvalidRequestError(
            message="Invalid parameter in request",
            details={"param": "doc_id", "reason": "Format not valid"}
        ),
        "ResourceNotFoundError": ResourceNotFoundError(
            message="Document not found",
            details={"doc_id": "missing-id-123"}
        ),
        "ValidationError": ValidationError(
            message="Validation failed for input data",
            locations=[{"field": "url", "message": "Not a valid URL"}]
        ),
        "DependencyError": DependencyError(
            message="Failed to connect to backend service",
            details={"service": "memory_store", "error": "Connection timeout"}
        )
    }

@pytest.mark.asyncio
async def test_error_handlers(test_request, test_errors):
    """Test that error handlers return properly formatted responses."""
    for error_name, error in test_errors.items():
        # Get response from the handler
        response = await nexus_harvester_exception_handler(test_request, error)
        
        # Convert response to dict for validation
        response_body = response.body.decode('utf-8')
        response_dict = json.loads(response_body)
        
        # Verify all required elements
        assert response.status_code == error.status_code, f"{error_name} returned wrong status code"
        assert response_dict["status"] == "error", f"{error_name} missing 'error' status"
        assert response_dict["code"] == error.status_code, f"{error_name} has incorrect code"
        assert response_dict["error_type"] == error.error_type, f"{error_name} wrong error_type"
        assert response_dict["message"] == error.message, f"{error_name} message mismatch"
        
        # Check contextual details are preserved
        if error.details:
            assert "details" in response_dict, f"{error_name} missing details"
            for key in error.details:
                assert key in response_dict["details"], f"{error_name} missing detail '{key}'"
        
        # Check that locations are preserved for validation errors
        if hasattr(error, 'locations') and error.locations:
            assert "locations" in response_dict, f"{error_name} missing locations"
            assert len(response_dict["locations"]) == len(error.locations), f"{error_name} location count mismatch"


@pytest.mark.asyncio
async def test_request_context_preservation(test_request, test_errors):
    """Test that request context (headers, path) is preserved in error responses."""
    # Test with resource not found error
    error = test_errors["ResourceNotFoundError"]
    response = await nexus_harvester_exception_handler(test_request, error)
    
    # Parse response
    response_dict = json.loads(response.body.decode('utf-8'))
    
    # Verify request_id is preserved from headers
    assert "request_id" in response_dict, "Request ID not included in response"
    assert response_dict["request_id"] == "test-123", "Request ID value mismatch"

@pytest.mark.asyncio
async def test_error_detail_fidelity(test_request):
    """Test that error details are preserved with full fidelity."""
    # Create an error with complex nested details
    error = DependencyError(
        message="Complex dependency failure",
        details={
            "service": "vector_db",
            "operation": "index",
            "metrics": {
                "attempts": 3,
                "timeout_ms": 5000,
                "last_error_code": "ETIMEDOUT"
            },
            "documents": [
                {"id": "doc1", "status": "failed"},
                {"id": "doc2", "status": "pending"}
            ]
        }
    )
    
    # Get response
    response = await nexus_harvester_exception_handler(test_request, error)
    response_dict = json.loads(response.body.decode('utf-8'))
    
    # Verify complex details are preserved with full fidelity
    assert "details" in response_dict, "Details missing from response"
    details = response_dict["details"]
    
    assert details["service"] == "vector_db", "Basic detail corrupted"
    assert "metrics" in details, "Nested object missing"
    assert details["metrics"]["attempts"] == 3, "Nested numeric value corrupted"
    assert len(details["documents"]) == 2, "Array length corrupted"
    assert details["documents"][0]["id"] == "doc1", "Array object value corrupted"
