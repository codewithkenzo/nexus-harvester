"""
Error handling utilities specific to rate limiting.

This module provides specialized error response creation for rate limiting
errors that follow the standard Nexus Harvester error format but work 
without a request object.
"""
from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional, cast

from fastapi import Request

from nexus_harvester.utils.errors import ErrorResponse


def create_rate_limit_response(
    error_type: str,
    message: str,
    detail: Optional[Dict[str, Any]] = None,
    status_code: int = 429,
    request_id: Optional[str] = None,
    include_traceback: bool = False
) -> ErrorResponse:
    """Create a standardized error response for rate limiting.
    
    This version does not require a Request object or exception, making it
    suitable for use in middleware contexts where those may not be available.
    
    Args:
        error_type: Type of error (e.g., 'rate_limit_exceeded')
        message: Human-readable error message
        detail: Additional error details
        status_code: HTTP status code (default: 429)
        request_id: Optional request identifier
        include_traceback: Whether to include traceback in development environments
    
    Returns:
        Standardized error response
    """
    # Get traceback if needed
    tb = None
    if include_traceback:
        tb = traceback.format_exc().splitlines()
    
    # Build error response
    return ErrorResponse(
        code=status_code,
        message=message,
        error_type=error_type,
        request_id=request_id,
        details=detail,
        locations=None,
        traceback=tb
    )
