"""Generate baseline chunking quality report from existing database.

Usage:
    python -m evaluation.baseline_report [--db-path PATH] [--output PATH]

This script analyzes all chunks in the database and produces a report
showing current chunking quality metrics.
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from evaluation.chunking_metrics import ChunkAnalyzer, analyze_document_chunks


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Connect to the database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_documents(conn: sqlite3.Connection) -> List[Dict]:
    """Get all documents with their file paths"""
    cursor = conn.execute("""
        SELECT id, file_path
        FROM documents
        ORDER BY file_path
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_chunks_for_document(conn: sqlite3.Connection, doc_id: int) -> List[str]:
    """Get all chunk contents for a document, ordered by chunk_index"""
    cursor = conn.execute("""
        SELECT content
        FROM chunks
        WHERE document_id = ?
        ORDER BY chunk_index
    """, (doc_id,))
    return [row['content'] for row in cursor.fetchall()]


def detect_content_type(file_path: str) -> str:
    """Detect content type from file extension"""
    ext = Path(file_path).suffix.lower()

    code_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
        '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift',
        '.kt', '.scala', '.r', '.jl', '.lua', '.sh', '.bash', '.zsh'
    }

    # .ipynb now uses HybridChunker which produces markdown-like chunks
    markdown_extensions = {'.md', '.markdown', '.rst', '.adoc', '.ipynb'}

    if ext in code_extensions:
        return 'code'
    elif ext in markdown_extensions:
        return 'markdown'
    else:
        return 'text'


def analyze_by_file_type(
    conn: sqlite3.Connection,
    documents: List[Dict]
) -> Dict[str, Dict]:
    """Analyze chunks grouped by file type"""
    analyzer = ChunkAnalyzer()
    by_type = defaultdict(lambda: {'chunks': [], 'doc_count': 0, 'files': []})

    for doc in documents:
        doc_id = doc['id']
        file_path = doc['file_path']
        chunks = get_chunks_for_document(conn, doc_id)

        if not chunks:
            continue

        content_type = detect_content_type(file_path)
        ext = Path(file_path).suffix.lower() or 'no_ext'

        by_type[ext]['chunks'].extend(chunks)
        by_type[ext]['doc_count'] += 1
        by_type[ext]['content_type'] = content_type
        by_type[ext]['files'].append(file_path)

    results = {}
    for ext, data in by_type.items():
        chunks = data['chunks']
        content_type = data.get('content_type', 'text')

        stats = analyzer.compute_stats(chunks)
        boundary = analyzer.analyze_boundary_coherence(chunks, content_type)

        results[ext] = {
            'file_extension': ext,
            'content_type': content_type,
            'document_count': data['doc_count'],
            'chunk_count': len(chunks),
            'stats': asdict(stats),
            'boundary_coherence': {
                'score': boundary.score,
                'total_boundaries': boundary.total_boundaries,
                'clean_boundaries': boundary.clean_boundaries,
                'mid_sentence_splits': boundary.mid_sentence_splits,
                'mid_word_splits': boundary.mid_word_splits
            }
        }

    return results


def get_overall_stats(conn: sqlite3.Connection) -> Dict:
    """Get overall database statistics"""
    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # Get total characters
    total_chars = conn.execute(
        "SELECT SUM(LENGTH(content)) FROM chunks"
    ).fetchone()[0] or 0

    # Documents with no chunks
    empty_docs = conn.execute("""
        SELECT COUNT(*) FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
    """).fetchone()[0]

    return {
        'total_documents': doc_count,
        'total_chunks': chunk_count,
        'total_characters': total_chars,
        'avg_chunks_per_doc': chunk_count / doc_count if doc_count > 0 else 0,
        'avg_chars_per_chunk': total_chars / chunk_count if chunk_count > 0 else 0,
        'documents_without_chunks': empty_docs
    }


def generate_report(db_path: str) -> Dict:
    """Generate full baseline report"""
    conn = get_db_connection(db_path)

    try:
        documents = get_all_documents(conn)
        overall = get_overall_stats(conn)
        by_type = analyze_by_file_type(conn, documents)

        # Sort by_type by chunk count descending
        sorted_types = dict(
            sorted(by_type.items(), key=lambda x: x[1]['chunk_count'], reverse=True)
        )

        # Compute aggregate boundary coherence
        total_boundaries = sum(t['boundary_coherence']['total_boundaries'] for t in by_type.values())
        clean_boundaries = sum(t['boundary_coherence']['clean_boundaries'] for t in by_type.values())
        overall_coherence = clean_boundaries / total_boundaries if total_boundaries > 0 else 1.0

        return {
            'generated_at': datetime.now().isoformat(),
            'database_path': db_path,
            'summary': {
                **overall,
                'overall_boundary_coherence': overall_coherence,
                'file_types_analyzed': len(by_type)
            },
            'by_file_type': sorted_types
        }

    finally:
        conn.close()


def print_report(report: Dict) -> None:
    """Print human-readable report to stdout"""
    print("=" * 60)
    print("CHUNKING QUALITY BASELINE REPORT")
    print("=" * 60)
    print(f"Generated: {report['generated_at']}")
    print(f"Database: {report['database_path']}")
    print()

    summary = report['summary']
    print("SUMMARY")
    print("-" * 40)
    print(f"Total documents:       {summary['total_documents']:,}")
    print(f"Total chunks:          {summary['total_chunks']:,}")
    print(f"Total characters:      {summary['total_characters']:,}")
    print(f"Avg chunks/doc:        {summary['avg_chunks_per_doc']:.1f}")
    print(f"Avg chars/chunk:       {summary['avg_chars_per_chunk']:.0f}")
    print(f"Boundary coherence:    {summary['overall_boundary_coherence']:.1%}")
    print(f"File types analyzed:   {summary['file_types_analyzed']}")
    if summary['documents_without_chunks'] > 0:
        print(f"Docs without chunks:   {summary['documents_without_chunks']}")
    print()

    print("BY FILE TYPE")
    print("-" * 40)
    print(f"{'Ext':<10} {'Docs':>6} {'Chunks':>8} {'Avg Size':>10} {'Coherence':>10}")
    print("-" * 40)

    for ext, data in report['by_file_type'].items():
        avg_size = data['stats']['avg_size']
        coherence = data['boundary_coherence']['score']
        print(f"{ext:<10} {data['document_count']:>6} {data['chunk_count']:>8} "
              f"{avg_size:>10.0f} {coherence:>10.1%}")

    print()
    print("SIZE DISTRIBUTION (all chunks)")
    print("-" * 40)

    # Aggregate size distribution
    total_dist = defaultdict(int)
    for data in report['by_file_type'].values():
        for bucket, count in data['stats']['size_distribution'].items():
            total_dist[bucket] += count

    for bucket in ['tiny (<100)', 'small (100-500)', 'medium (500-2000)',
                   'large (2000-5000)', 'huge (>5000)']:
        count = total_dist[bucket]
        pct = count / summary['total_chunks'] * 100 if summary['total_chunks'] > 0 else 0
        bar = '#' * int(pct / 2)
        print(f"{bucket:<20} {count:>8} ({pct:>5.1f}%) {bar}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate chunking quality baseline report'
    )
    parser.add_argument(
        '--db-path',
        default='data/knowledge_base.db',
        help='Path to database (default: data/knowledge_base.db)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output JSON file path (if not specified, prints to stdout)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of human-readable'
    )

    args = parser.parse_args()

    # Check database exists
    if not Path(args.db_path).exists():
        print(f"Error: Database not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    report = generate_report(args.db_path)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {args.output}")
    elif args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == '__main__':
    main()
