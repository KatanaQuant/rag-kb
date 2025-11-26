"""Document listing service

Provides document listing for API routes.
Supports both sync and async vector stores.
"""
from typing import List


class DocumentLister:
    """Lists indexed documents"""

    def __init__(self, vector_store):
        self.store = vector_store

    async def list_all(self) -> dict:
        """List all documents (async for non-blocking database)"""
        cursor = await self._query()
        documents = await self._format(cursor)
        return self._build_response(documents)

    async def _query(self):
        """Query documents (async)"""
        return await self.store.query_documents_with_chunks()

    @staticmethod
    async def _format(cursor) -> List[dict]:
        """Format results (async to iterate cursor)"""
        documents = []
        async for row in cursor:
            DocumentLister._add_doc(documents, row)
        return documents

    @staticmethod
    def _add_doc(documents: List, row):
        """Add document to list"""
        documents.append({
            'file_path': row[0],
            'indexed_at': row[1],
            'chunk_count': row[2]
        })

    @staticmethod
    def _build_response(documents: List) -> dict:
        """Build response dict"""
        return {
            'total_documents': len(documents),
            'documents': documents
        }
