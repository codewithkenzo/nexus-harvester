"""Centralized logging configuration for Nexus Harvester.

This module sets up a structured logging system using structlog to ensure
consistent, contextual logging across the application. It provides:

1. Development and production logging configurations
2. Context variables for request tracking
3. Structured log output (pretty in dev, JSON in prod)
4. Standardized log levels and formatting
"""

import logging
import sys
import time
import uuid
from typing import Any, Dict, Optional, Union, cast

import structlog
from pydantic import BaseModel
from structlog.types import EventDict, Processor, WrappedLogger

# Define contextvars for storing request context
from contextvars import ContextVar

# Context variables to store request-specific data
request_id: ContextVar[str] = ContextVar("request_id", default="")
session_id: ContextVar[str] = ContextVar("session_id", default="")
doc_id: ContextVar[str] = ContextVar("doc_id", default="")
component: ContextVar[str] = ContextVar("component", default="")


class LogConfig(BaseModel):
    """Logging configuration model."""
    
    # General settings
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = False
    
    # Log format settings
    CONSOLE_LOG_FORMAT: str = "%(levelprefix)s %(message)s"
    JSON_LOG_FORMAT: str = "%(message)s"
    LOG_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """
    Set up structured logging for the application.
    
    Args:
        config: Optional logging configuration
    """
    if config is None:
        config = LogConfig()
    
    # Standard processors for all environments
    shared_processors = [
        # Add timestamp to all logs
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
        # Add log level to all logs
        structlog.stdlib.add_log_level,
        # Extract logger name
        structlog.stdlib.add_logger_name,
        # Add context vars to all logs
        add_context_vars,
    ]
    
    # Configure structlog based on environment
    if config.ENVIRONMENT.lower() == "production":
        # Production configuration with JSON formatting
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # Development configuration with pretty console output
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    # Configure standard logging to work with structlog
    logging.basicConfig(
        format=config.CONSOLE_LOG_FORMAT if not config.JSON_LOGS else config.JSON_LOG_FORMAT,
        level=config.LOG_LEVEL,
        stream=sys.stdout,
    )


def add_context_vars(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add context variables to log events.
    
    Args:
        logger: The wrapped logger
        method_name: The method being called
        event_dict: The event dictionary
        
    Returns:
        EventDict with added context
    """
    # Add request context if available
    req_id = request_id.get()
    if req_id:
        event_dict["request_id"] = req_id
    
    # Add session context if available
    sess_id = session_id.get()
    if sess_id:
        event_dict["session_id"] = sess_id
    
    # Add document context if available
    document_id = doc_id.get()
    if document_id:
        event_dict["doc_id"] = document_id
    
    # Add component context if available
    comp = component.get()
    if comp:
        event_dict["component"] = comp
    
    return event_dict


def get_logger(name: Optional[str] = None, **initial_values: Any) -> structlog.BoundLogger:
    """
    Get a configured logger with optional initial values.
    
    Args:
        name: Logger name (usually module name)
        **initial_values: Initial values to bind to the logger
        
    Returns:
        Configured structlog logger
    """
    logger = structlog.get_logger(name)
    
    if initial_values:
        logger = logger.bind(**initial_values)
        
    return logger


def bind_request_id(req_id: str) -> None:
    """
    Bind request ID to the current context.
    
    Args:
        req_id: Request ID to bind
    """
    request_id.set(req_id)


def bind_session_id(sess_id: str) -> None:
    """
    Bind session ID to the current context.
    
    Args:
        sess_id: Session ID to bind
    """
    session_id.set(sess_id)


def bind_doc_id(document_id: str) -> None:
    """
    Bind document ID to the current context.
    
    Args:
        document_id: Document ID to bind
    """
    doc_id.set(document_id)


def bind_component(comp_name: str) -> None:
    """
    Bind component name to the current context.
    
    Args:
        comp_name: Component name to bind
    """
    component.set(comp_name)


def clear_context() -> None:
    """Clear all context variables."""
    request_id.set("")
    session_id.set("")
    doc_id.set("")
    component.set("")


class RequestLoggingMiddleware:
    """
    FastAPI middleware for request logging.
    
    This middleware:
    1. Generates a unique request ID if not present
    2. Logs request details
    3. Times request duration
    4. Logs response details
    """
    
    async def __call__(self, request, call_next):
        """Process the request and log details."""
        # Generate or get request ID
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        bind_request_id(req_id)
        
        # Get the logger for the middleware
        logger = get_logger("api.middleware")
        
        # Log request received
        start_time = time.time()
        logger.info(
            "Request received",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
        )
        
        # Process the request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            # Log response details
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = req_id
            
            return response
        except Exception as e:
            # Log exception
            logger.exception(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
            )
            raise
        finally:
            # Clear context
            clear_context()

# Initialize logging on module import
setup_logging()
