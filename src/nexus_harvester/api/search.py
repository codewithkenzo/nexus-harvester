"""API endpoints for document search."""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator

import orjson
from fastapi import APIRouter, Query, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from nexus_harvester.clients.mem0 import Mem0Client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["Search"])


def get_mem0_client() -> Mem0Client:
    """Get the Mem0 client instance."""
    from nexus_harvester.api.dependencies import get_mem0_client as get_client
    return get_client()


@router.get("/")
async def search_documents(
    query: str = Query(..., description="Search query"),
    filters: Optional[str] = Query(None, description="JSON-encoded filters"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return")
):
    """Search indexed documents."""
    try:
        # Parse filters if provided
        filter_dict = None
        if filters:
            try:
                filter_dict = json.loads(filters)
                if not isinstance(filter_dict, dict):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Filters must be a valid JSON object"
                    )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Filters must be a valid JSON string"
                )
        
        # Get Mem0 client
        mem0_client = get_mem0_client()
        
        # Execute search
        logger.info(f"Executing search: {query} (filters: {filter_dict}, limit: {limit})")
        results = await mem0_client.search(
            query=query,
            filters=filter_dict,
            limit=limit
        )
        
        return {
            "query": query,
            "results": results,
            "count": len(results)
        }
    
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/stream")
async def stream_search(
    query: str = Query(..., description="Search query"),
    filters: Optional[str] = Query(None, description="JSON-encoded filters"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return")
):
    """Stream search results as Server-Sent Events (SSE)."""
    # Parse filters if provided
    filter_dict = None
    if filters:
        try:
            filter_dict = json.loads(filters)
            if not isinstance(filter_dict, dict):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Filters must be a valid JSON object"
                )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Filters must be a valid JSON string"
            )
    
    return StreamingResponse(
        event_generator(query, filter_dict, limit),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


async def event_generator(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 10
) -> AsyncGenerator[str, None]:
    """Generate SSE events for search results."""
    # Initial response
    yield f"data: {orjson.dumps({'status': 'processing'}).decode()}\n\n"
    
    try:
        # Get Mem0 client
        mem0_client = get_mem0_client()
        
        # Execute search
        logger.info(f"Executing streaming search: {query} (filters: {filters}, limit: {limit})")
        results = await mem0_client.search(
            query=query,
            filters=filters,
            limit=limit
        )
        
        # Stream results
        for result in results:
            yield f"data: {orjson.dumps(result).decode()}\n\n"
            await asyncio.sleep(0.05)  # Small delay for smooth streaming
        
        # Final event
        yield f"data: {orjson.dumps({'status': 'complete', 'total': len(results)}).decode()}\n\n"
    
    except Exception as e:
        # Error event
        logger.error(f"Streaming search failed: {str(e)}", exc_info=True)
        yield f"data: {orjson.dumps({'status': 'error', 'message': str(e)}).decode()}\n\n"
