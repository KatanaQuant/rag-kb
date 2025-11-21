from typing import List, Dict


class DocumentLister:
    """Lists indexed documents"""

    def __init__(self, vector_store):
        self.store = vector_store

    def list_all(self) -> dict:
        """List all documents"""
        cursor = self._query()
        documents = self._format(cursor)
        return self._build_response(documents)

    def _query(self):
        """Query documents"""
        return self.store.query_documents_with_chunks()

    @staticmethod
    def _format(cursor) -> List[dict]:
        """Format results"""
        documents = []
        for row in cursor:
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

