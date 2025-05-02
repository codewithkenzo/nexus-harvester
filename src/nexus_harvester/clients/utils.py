"""Utility functions for client operations."""

import logging
from typing import Optional

import httpx
from pydantic import HttpUrl

# Set up logging
logger = logging.getLogger(__name__)


async def fetch_document(url: HttpUrl, timeout: int = 30) -> str:
    """
    Fetch document content from a URL.
    
    Args:
        url: The URL to fetch the document from
        timeout: Timeout in seconds for the HTTP request
        
    Returns:
        The document content as a string
        
    Raises:
        Exception: If the document cannot be fetched
    """
    logger.info(f"Fetching document from URL: {url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                str(url),
                timeout=timeout,
                follow_redirects=True
            )
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as e:
        logger.error(f"Error fetching document from URL {url}: {str(e)}")
        raise Exception(f"Failed to fetch document: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching document from URL {url}: {str(e)}")
        raise Exception(f"Failed to fetch document: {str(e)}")
