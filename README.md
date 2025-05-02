# Nexus Harvester

## Overview
The Nexus Harvester is our core ingestion, chunking, and search service that processes and stores documents for retrieval. It serves as the foundation for our RAG capabilities. Built with Python 3.12+ and FastAPI, it provides high-performance document processing and retrieval with streaming capabilities.

## Architecture

### Production Backends
- **Zep**: Primary memory-related operations (session, summarization, knowledge graph)
- **Mem0**: Primary search capabilities (search, batch operations, metadata filtering)

### Development Backend
- **Qdrant**: Used for development/testing only, not deployed in production

## Pipeline Stages

1. **Ingestion**: Handles document acquisition from various sources
2. **Chunking**: Breaks documents into smaller, processable pieces
3. **Enrichment**: Adds metadata and context to chunks
4. **Indexing**: Stores chunks in appropriate backend services

## Key Features

- HTTP/SSE streaming for real-time updates
- Pydantic model validation throughout the pipeline
- Async processing for high-throughput operations
- MCP tool interfaces for agent integration
- Structured logging with context tracking
- Dual backend architecture (Zep + Mem0)

## API Endpoints

### REST API
- `POST /ingest`: Submit document for processing
- `GET /search`: Search for documents with filtering
- `GET /search/stream`: Stream search results via SSE

### MCP Tools
- `ingest_document`: Process and store document
- `search_knowledge`: Search stored knowledge
- `get_memory`: Retrieve memory context

## Folder Structure
```
nexus_harvester/
├── src/
│   ├── nexus_harvester/
│   │   ├── api/            # FastAPI endpoints
│   │   ├── clients/        # Backend clients (Zep, Mem0)
│   │   ├── ingestion/      # Document ingestion logic
│   │   ├── processing/     # Chunking and processing
│   │   ├── indexing/       # Indexing to backends
│   │   ├── search/         # Search implementation
│   │   ├── mcp/            # MCP tool definitions
│   │   ├── utils/          # Utility modules (logging, etc.)
│   │   ├── models.py       # Core data models
│   │   ├── settings.py     # Application settings
│   │   └── main.py         # Main application entry point
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── docs/                  # Detailed documentation
└── configs/               # Configuration files
```

## Configuration

The Knowledge Harvester uses Pydantic settings for configuration:
```python
class KnowledgeHarvesterSettings(BaseSettings):
    # Service configuration
    service_name: str = "knowledge-harvester"
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Zep configuration
    zep_api_url: HttpUrl
    zep_api_key: SecretStr
    
    # Mem0 configuration
    mem0_api_url: HttpUrl
    mem0_api_key: SecretStr
    
    # Development only
    use_qdrant_dev: bool = False
    qdrant_url: Optional[HttpUrl] = None
    
    # Processing settings
    chunk_size: int = 512
    chunk_overlap: int = 128
```

## Setup and Development

### Prerequisites
- Python 3.12+
- Poetry for dependency management
- Docker and Docker Compose
- Access to Zep and Mem0 instances

### Local Development
```bash
# Clone the repository
git clone https://github.com/your-org/nexus-harvester.git

# Set up environment
cd nexus-harvester
poetry install
poetry shell

# Start the service
python -m src.nexus_harvester.main
```

### Docker Deployment
```bash
docker-compose up -d
```

## Implementation Status

Current status of implementation (2025-05-02):

| Feature | Status | Progress | Notes |
|---------|--------|----------|-------|
| Project Setup | Completed | 100% | Basic structure and dependencies |
| Core Models | Completed | 100% | Document and Chunk models implemented |
| Zep Integration | In Progress | 80% | Client interface and testing |
| Mem0 Integration | In Progress | 80% | Client interface and testing |
| Document Processing | In Progress | 30% | Basic chunking implemented |
| Indexing Service | In Progress | 95% | Implementation, testing, and comprehensive logging |
| Logging System | In Progress | 90% | Structured logging with context variables |
| REST API Endpoints | Completed | 70% | Ingestion and search endpoints implemented |
| MCP Tools | In Progress | 60% | Initial implementation |
| Testing Suite | In Progress | 60% | Unit tests for IndexingService, API, and MCP tools |

## TODO List

- [x] Project setup and dependency management
- [x] Core data models with Pydantic
- [x] Backend client interfaces
- [x] Basic document processing
- [x] Implement indexing service
- [x] Create REST API endpoints for document ingestion
- [x] Create REST API endpoints for search
- [x] Implement MCP tools for agent integration
- [x] Implement comprehensive structured logging
- [ ] Complete error handling in API endpoints
- [ ] Implement validation for document processing parameters
- [ ] Add rate limiting for API endpoints
- [ ] Complete comprehensive test suite
- [ ] Set up CI/CD pipeline
- [ ] Create Docker deployment configuration
- [ ] Add documentation for API and usage