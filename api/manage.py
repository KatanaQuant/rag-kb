#!/usr/bin/env python3
"""
RAG Knowledge Base Maintenance CLI

Usage:
    python manage.py health              # Check completeness health
    python manage.py fix-tracking        # Backfill chunk counts
    python manage.py delete-orphans      # Delete orphan document records
    python manage.py list-rejected       # List rejected files
    python manage.py list-incomplete     # List incomplete documents
    python manage.py reindex-incomplete  # Re-index all incomplete documents

Via docker:
    docker-compose exec rag-api python manage.py health
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# Add api directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def get_db_path() -> str:
    """Get database path"""
    try:
        from config import default_config
        return default_config.database.path
    except ImportError:
        return "/app/data/rag.db"


def cmd_health(args):
    """Check completeness health"""
    import requests

    try:
        resp = requests.get('http://localhost:8000/documents/completeness', timeout=300)
        data = resp.json()

        print(f"Total documents: {data['total_documents']}")
        print(f"Complete:        {data['complete']}")
        print(f"Incomplete:      {data['incomplete']}")

        if data['incomplete'] > 0:
            print(f"\nIssue breakdown:")
            from collections import Counter
            issues = Counter(i['issue'] for i in data['issues'])
            for issue, count in issues.most_common():
                print(f"  {issue}: {count}")

            if args.verbose:
                print(f"\nIncomplete documents:")
                for i in data['issues'][:20]:
                    print(f"  {i['file_path'].split('/')[-1]}: {i['issue']}")
                if len(data['issues']) > 20:
                    print(f"  ... and {len(data['issues']) - 20} more")

        return 0 if data['incomplete'] == 0 else 1

    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API. Is the server running?")
        return 1


def cmd_fix_tracking(args):
    """Backfill chunk counts for historical documents"""
    from migrations.backfill_chunk_counts import backfill_chunk_counts

    result = backfill_chunk_counts(dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nRun without --dry-run to apply {result['would_update']} updates")
    else:
        print(f"\nDone. Run 'python manage.py health' to verify.")

    return 0


def cmd_delete_orphans(args):
    """Delete orphan document records (metadata with no chunks)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)

    # Find orphans
    orphans = conn.execute('''
        SELECT d.id, d.file_path
        FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
    ''').fetchall()

    if not orphans:
        print("No orphan documents found.")
        return 0

    print(f"Found {len(orphans)} orphan documents")

    if args.dry_run:
        print("\nDRY RUN - Would delete:")
        for doc_id, fp in orphans[:10]:
            print(f"  {fp.split('/')[-1]}")
        if len(orphans) > 10:
            print(f"  ... and {len(orphans) - 10} more")
        print(f"\nRun without --dry-run to delete")
        return 0

    # Confirm
    if not args.yes:
        confirm = input(f"Delete {len(orphans)} orphan records? [y/N] ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return 0

    # Delete
    deleted_docs = 0
    deleted_progress = 0
    for doc_id, file_path in orphans:
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        deleted_docs += 1
        result = conn.execute('DELETE FROM processing_progress WHERE file_path = ?', (file_path,))
        deleted_progress += result.rowcount

    conn.commit()
    conn.close()

    print(f"Deleted {deleted_docs} document records")
    print(f"Deleted {deleted_progress} progress records")
    return 0


def cmd_list_rejected(args):
    """List rejected files"""
    from ingestion.progress import ProcessingProgressTracker

    db_path = get_db_path()
    tracker = ProcessingProgressTracker(db_path)
    rejected = tracker.get_rejected_files()

    if not rejected:
        print("No rejected files found.")
        return 0

    print(f"Rejected files ({len(rejected)} total):\n")

    for r in rejected:
        filename = Path(r.file_path).name
        check_name = ""
        reason = r.error_message or "Unknown reason"

        # Extract check name from error message if present
        if "(" in reason and ")" in reason:
            check_name = reason[reason.find("(")+1:reason.find(")")]
            reason = reason[reason.find(":")+2:].strip() if ":" in reason else reason

        print(f"  {filename}")
        print(f"    Path: {r.file_path}")
        print(f"    Reason: {reason}")
        if r.last_updated:
            print(f"    Rejected: {r.last_updated}")
        print()

    return 0


def cmd_list_incomplete(args):
    """List incomplete documents"""
    import requests

    try:
        resp = requests.get('http://localhost:8000/documents/completeness', timeout=300)
        data = resp.json()

        if data['incomplete'] == 0:
            print("All documents are complete!")
            return 0

        print(f"Incomplete documents ({data['incomplete']} total):\n")

        # Group by issue type
        by_issue = {}
        for i in data['issues']:
            issue = i['issue']
            if issue not in by_issue:
                by_issue[issue] = []
            by_issue[issue].append(i)

        for issue, items in by_issue.items():
            print(f"## {issue} ({len(items)} documents)")
            limit = args.limit if args.limit else 10
            for item in items[:limit]:
                print(f"  {item['file_path'].split('/')[-1]}: {item['message']}")
            if len(items) > limit:
                print(f"  ... and {len(items) - limit} more")
            print()

        return 0

    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API. Is the server running?")
        return 1


def cmd_reindex_incomplete(args):
    """Re-index all incomplete documents"""
    import requests

    try:
        # Get incomplete documents
        resp = requests.get('http://localhost:8000/documents/completeness', timeout=300)
        data = resp.json()

        incomplete = [i for i in data['issues']
                      if i['issue'] in ('zero_chunks', 'processing_incomplete', 'missing_embeddings')]

        if not incomplete:
            print("No documents need re-indexing.")
            return 0

        print(f"Found {len(incomplete)} documents that may need re-indexing")

        if args.dry_run:
            print("\nDRY RUN - Would re-index:")
            for item in incomplete[:10]:
                print(f"  {item['file_path'].split('/')[-1]}")
            if len(incomplete) > 10:
                print(f"  ... and {len(incomplete) - 10} more")
            print("\nRun without --dry-run to re-index")
            return 0

        # Confirm
        if not args.yes:
            confirm = input(f"Re-index {len(incomplete)} documents? [y/N] ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return 0

        # Re-index each
        success = 0
        failed = 0
        for item in incomplete:
            path = item['file_path']
            try:
                resp = requests.post(
                    f'http://localhost:8000/documents/reindex',
                    params={'path': path, 'force': 'true'},
                    timeout=300
                )
                if resp.status_code == 200:
                    print(f"  ✓ {path.split('/')[-1]}")
                    success += 1
                else:
                    print(f"  ✗ {path.split('/')[-1]}: {resp.status_code}")
                    failed += 1
            except Exception as e:
                print(f"  ✗ {path.split('/')[-1]}: {e}")
                failed += 1

        print(f"\nDone: {success} succeeded, {failed} failed")
        return 0 if failed == 0 else 1

    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API. Is the server running?")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='RAG Knowledge Base Maintenance CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # health
    p = subparsers.add_parser('health', help='Check completeness health')
    p.add_argument('-v', '--verbose', action='store_true', help='Show incomplete documents')
    p.set_defaults(func=cmd_health)

    # fix-tracking
    p = subparsers.add_parser('fix-tracking', help='Backfill chunk counts for historical data')
    p.add_argument('--dry-run', action='store_true', help='Show what would change')
    p.set_defaults(func=cmd_fix_tracking)

    # delete-orphans
    p = subparsers.add_parser('delete-orphans', help='Delete orphan document records')
    p.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    p.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')
    p.set_defaults(func=cmd_delete_orphans)

    # list-rejected
    p = subparsers.add_parser('list-rejected', help='List rejected files')
    p.set_defaults(func=cmd_list_rejected)

    # list-incomplete
    p = subparsers.add_parser('list-incomplete', help='List incomplete documents')
    p.add_argument('-l', '--limit', type=int, help='Limit per category')
    p.set_defaults(func=cmd_list_incomplete)

    # reindex-incomplete
    p = subparsers.add_parser('reindex-incomplete', help='Re-index incomplete documents')
    p.add_argument('--dry-run', action='store_true', help='Show what would be re-indexed')
    p.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')
    p.set_defaults(func=cmd_reindex_incomplete)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
