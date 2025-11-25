"""
Document routes module

Extracted from main.py following POODR principles:
- Single responsibility: document operations only
- Dependency injection via FastAPI Request
"""
from fastapi import APIRouter, Request, HTTPException
from typing import List
import sqlite3

from models import DocumentInfoResponse
from config import default_config

router = APIRouter()


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


class DocumentSearcher:
    """Searches for documents in database"""

    def search(self, pattern: str = None) -> dict:
        """Search documents by pattern"""
        results = self._query_documents(pattern)
        documents = self._format_results(results)
        return self._build_response(pattern, documents)

    def _query_documents(self, pattern: str = None):
        """Query documents with optional pattern"""
        conn = sqlite3.connect(default_config.database.path)

        if pattern:
            results = self._search_with_pattern(conn, pattern)
        else:
            results = self._list_all_documents(conn)

        conn.close()
        return results

    def _search_with_pattern(self, conn, pattern: str):
        """Search with pattern filter"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE d.file_path LIKE ?
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """, (f"%{pattern}%",))
        return cursor.fetchall()

    def _list_all_documents(self, conn):
        """List all documents"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """)
        return cursor.fetchall()

    def _format_results(self, results):
        """Format query results"""
        return [self._format_row(row) for row in results]

    def _format_row(self, row) -> dict:
        """Format single row"""
        return {
            "id": row[0],
            "file_path": row[1],
            "file_name": row[1].split('/')[-1],
            "file_hash": row[2],
            "indexed_at": row[3],
            "chunk_count": row[4]
        }

    def _build_response(self, pattern, documents):
        """Build search response"""
        return {
            "pattern": pattern,
            "total_matches": len(documents),
            "documents": documents
        }


@router.get("/document/{filename}", response_model=DocumentInfoResponse)
async def get_document_info(filename: str, request: Request):
    """Get document information including extraction method"""
    try:
        app_state = request.app.state.app_state
        info = app_state.core.vector_store.get_document_info(filename)
        if not info:
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
        return DocumentInfoResponse(**info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve document info")


@router.get("/documents")
async def list_documents(request: Request):
    """List all documents"""
    try:
        app_state = request.app.state.app_state
        lister = DocumentLister(app_state.core.vector_store)
        return lister.list_all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to list documents"
        )


@router.get("/documents/search")
async def search_documents(pattern: str = None):
    """Search for documents by file path pattern

    Args:
        pattern: Optional substring to search for in file paths (case-insensitive)
                 Examples: "AFTS", "notebook", ".pdf", "chapter1"

    Returns:
        List of matching documents with their metadata
    """
    try:
        searcher = DocumentSearcher()
        return searcher.search(pattern)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search documents: {str(e)}"
        )


@router.delete("/document/{file_path:path}")
async def delete_document(file_path: str, request: Request):
    """Delete a document and all its chunks from the vector store

    This removes:
    - Document record from documents table
    - All chunks from chunks table
    - Processing progress from processing_progress table

    Args:
        file_path: Full path to the document (e.g., /app/knowledge_base/file.pdf)

    Returns:
        Deletion statistics including chunks deleted
    """
    try:
        app_state = request.app.state.app_state
        # Delete from vector store (documents + chunks)
        result = app_state.core.vector_store.delete_document(file_path)

        # Delete from processing progress
        if app_state.core.progress_tracker:
            try:
                app_state.core.progress_tracker.delete_document(file_path)
            except Exception as e:
                print(f"Warning: Failed to delete progress record: {e}")

        return {
            "status": "success",
            "file_path": file_path,
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )
