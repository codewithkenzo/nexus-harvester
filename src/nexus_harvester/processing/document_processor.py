"""Document processing and chunking module."""

from typing import List
from uuid import UUID

from nexus_harvester.models import DocumentMeta, Chunk


class DocumentProcessor:
    """Process and chunk documents."""
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    async def process_document(self, doc_meta: DocumentMeta, content: str) -> List[Chunk]:
        """Process document and split into chunks."""
        # Basic chunking strategy - can be replaced with more sophisticated approach
        chunks = []
        text_length = len(content)
        start = 0
        
        chunk_index = 0
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_text = content[start:end]
            
            chunks.append(Chunk(
                doc_id=doc_meta.id,
                text=chunk_text,
                index=chunk_index,
                metadata={
                    "title": doc_meta.title,
                    "source": doc_meta.source,
                    "url": str(doc_meta.url)
                }
            ))
            
            chunk_index += 1
            start = end - self.chunk_overlap
        
        return chunks
