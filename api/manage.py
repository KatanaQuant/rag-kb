#!/usr/bin/env python3
"""
RAG Knowledge Base Maintenance CLI

Usage:
    python manage.py health                 # Check completeness health
    python manage.py fix-tracking           # Backfill chunk counts
    python manage.py delete-orphans         # Delete orphan document records
    python manage.py list-rejected          # List rejected files
    python manage.py quarantine-list        # List quarantined files
    python manage.py quarantine-restore     # Restore file from quarantine
    python manage.py quarantine-purge       # Purge old quarantined files
    python manage.py list-incomplete        # List incomplete documents
    python manage.py reindex-incomplete     # Re-index all incomplete documents
    python manage.py scan-existing          # Scan existing files for security issues

Via docker:
    docker-compose exec rag-api python manage.py health
    docker-compose exec rag-api python manage.py scan-existing
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


def cmd_quarantine_list(args):
    """List quarantined files"""
    from services.quarantine_manager import QuarantineManager
    from config import default_config

    manager = QuarantineManager(default_config.paths.knowledge_base)
    quarantined = manager.list_quarantined()

    if not quarantined:
        print("No files in quarantine.")
        return 0

    print(f"Quarantined files ({len(quarantined)} total):\n")

    for q in quarantined:
        filename = Path(q.original_path).name
        print(f"  {filename}.REJECTED")
        print(f"    Original: {q.original_path}")
        print(f"    Reason: {q.reason}")
        print(f"    Check: {q.validation_check}")
        print(f"    Quarantined: {q.quarantined_at}")
        print()

    return 0


def cmd_quarantine_restore(args):
    """Restore file from quarantine"""
    from services.quarantine_manager import QuarantineManager
    from config import default_config

    manager = QuarantineManager(default_config.paths.knowledge_base)

    if not args.filename:
        print("Error: --filename required")
        return 1

    success = manager.restore_file(args.filename, force=args.force)
    return 0 if success else 1


def cmd_quarantine_purge(args):
    """Purge old quarantined files"""
    from services.quarantine_manager import QuarantineManager
    from config import default_config

    manager = QuarantineManager(default_config.paths.knowledge_base)

    if args.dry_run:
        print(f"DRY RUN - Would purge files older than {args.days} days:\n")

    purged = manager.purge_old_files(args.days, dry_run=args.dry_run)

    if purged == 0:
        print(f"No files older than {args.days} days found.")
    else:
        if args.dry_run:
            print(f"\nRun without --dry-run to purge {purged} files")
        else:
            print(f"\nPurged {purged} files")

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


def cmd_scan_existing(args):
    """Scan existing files in knowledge base for security issues

    Retroactively validates all files currently in the knowledge base directory.
    Runs all enabled security checks (ClamAV, YARA, hash blacklist, file type validation).

    Severity levels:
    - CRITICAL: Confirmed malware (auto-quarantined by default)
    - WARNING: Suspicious patterns (logged, user decides)

    CRITICAL detections (ClamAV virus, hash blacklist) are auto-quarantined.
    Use --no-quarantine to disable auto-quarantine for CRITICAL.
    Use --force-quarantine to also quarantine WARNING level matches.
    """
    from config import default_config
    from ingestion.file_type_validator import FileTypeValidator
    from ingestion.validation_result import SecuritySeverity
    from services.quarantine_manager import QuarantineManager, QUARANTINE_CHECKS
    from ingestion.helpers import FileHasher

    kb_path = Path(default_config.paths.knowledge_base)
    validator = FileTypeValidator()
    quarantine = QuarantineManager(kb_path)
    hasher = FileHasher()
    db_path = get_db_path()

    # Find all files in knowledge base
    all_files = []
    for ext in ['.pdf', '.md', '.markdown', '.docx', '.epub', '.py', '.java',
                '.ts', '.tsx', '.js', '.jsx', '.cs', '.go', '.ipynb', '.txt']:
        all_files.extend(kb_path.rglob(f'*{ext}'))

    # Exclude quarantine directory and problematic directory
    all_files = [f for f in all_files
                 if '.quarantine' not in f.parts and 'problematic' not in f.parts]

    if not all_files:
        print("No files found in knowledge base.")
        return 0

    print(f"Scanning {len(all_files)} files in knowledge base...\n")

    # Categorize by severity
    clean_files = []
    critical_files = []  # CRITICAL: auto-quarantine (ClamAV, hash blacklist)
    warning_files = []   # WARNING: log only (YARA, non-dangerous validation failures)

    for file_path in all_files:
        # Run validation
        result = validator.validate(file_path)

        # Determine if this is truly CRITICAL (quarantinable)
        is_critical = (
            result.severity == SecuritySeverity.CRITICAL or
            (not result.is_valid and result.validation_check in QUARANTINE_CHECKS)
        )

        if result.is_valid and not result.matches:
            clean_files.append(file_path)
            if args.verbose:
                print(f"  ✓ {file_path.name}")

        elif is_critical:
            # CRITICAL: confirmed malware - AUTO-QUARANTINE by default
            critical_files.append((file_path, result))
            file_hash = hasher.hash_file(file_path)
            print(f"\n  🚨 CRITICAL: {file_path.name}")
            print(f"      Severity: CRITICAL (confirmed threat)")
            print(f"      Reason: {result.reason}")
            print(f"      Check: {result.validation_check}")
            print(f"      Hash: {file_hash}")

            # Auto-quarantine CRITICAL unless --no-quarantine
            if not args.no_quarantine:
                quarantined = quarantine.quarantine_file(
                    file_path,
                    result.reason,
                    result.validation_check,
                    file_hash
                )
                if quarantined:
                    print(f"      → Auto-quarantined")

                    # Delete from database
                    deleted = _delete_document_from_db(db_path, file_path)
                    if deleted:
                        print(f"      → Removed from database ({deleted} chunks deleted)")
            else:
                print(f"      → Quarantine skipped (--no-quarantine)")

        elif result.severity == SecuritySeverity.WARNING or result.matches or not result.is_valid:
            # WARNING: suspicious but not confirmed
            warning_files.append((file_path, result))
            file_hash = hasher.hash_file(file_path)
            print(f"\n  ⚠️  WARNING: {file_path.name}")
            print(f"      Severity: WARNING (suspicious pattern)")
            print(f"      Reason: {result.reason}")
            print(f"      Check: {result.validation_check}")

            # Show match details
            for match in result.matches:
                print(f"      Match: {match.rule_name}")
                if match.context:
                    print(f"             {match.context}")
                if match.offset:
                    print(f"             Offset: 0x{match.offset:X}")

            # Actionable guidance
            print(f"      Actions:")
            print(f"        - Review file manually")
            print(f"        - Allowlist: echo '{file_hash}' >> data/security_allowlist.txt")
            if args.force_quarantine:
                quarantined = quarantine.quarantine_file(
                    file_path, result.reason, result.validation_check, file_hash
                )
                if quarantined:
                    print(f"      → Force-quarantined")

    # Summary
    print(f"\n{'='*80}")
    print(f"Scan complete:")
    print(f"  Clean files:     {len(clean_files)}")
    quarantine_status = "(auto-quarantined)" if not args.no_quarantine else "(quarantine disabled)"
    print(f"  Critical (🚨):   {len(critical_files)} {quarantine_status}")
    print(f"  Warnings (⚠️):    {len(warning_files)} (review recommended)")

    if critical_files:
        print(f"\nCRITICAL files (confirmed threats):")
        for file_path, result in critical_files:
            status = "quarantined" if not args.no_quarantine else "NOT quarantined"
            print(f"  🚨 {file_path.name}: {result.reason} [{status}]")

    if warning_files:
        print(f"\nWARNING files (non-critical - review recommended):")
        for file_path, result in warning_files[:10]:  # Show first 10
            print(f"  ⚠️  {file_path.name}: {result.reason}")
        if len(warning_files) > 10:
            print(f"  ... and {len(warning_files) - 10} more")
        print(f"\n  To allowlist a file after manual review:")
        print(f"    sha256sum <filename> >> data/security_allowlist.txt")

    if critical_files and args.no_quarantine:
        print(f"\n⚠️  {len(critical_files)} CRITICAL files found but NOT quarantined!")
        print(f"   Run without --no-quarantine to auto-quarantine them")

    print(f"{'='*80}\n")

    return 0 if len(critical_files) == 0 else 1


def _delete_document_from_db(db_path: str, file_path: Path) -> int:
    """Delete document and its chunks from database

    Args:
        db_path: Path to database
        file_path: Path to the quarantined file

    Returns:
        Number of chunks deleted (0 if not found)
    """
    conn = sqlite3.connect(db_path)
    try:
        # Find the document by file path
        cursor = conn.execute(
            'SELECT id FROM documents WHERE file_path LIKE ?',
            (f'%{file_path.name}',)
        )
        row = cursor.fetchone()

        if not row:
            return 0

        doc_id = row[0]

        # Count chunks before deletion
        cursor = conn.execute(
            'SELECT COUNT(*) FROM chunks WHERE document_id = ?',
            (doc_id,)
        )
        chunk_count = cursor.fetchone()[0]

        # Delete chunks first (foreign key constraint)
        conn.execute('DELETE FROM chunks WHERE document_id = ?', (doc_id,))

        # Delete document
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))

        conn.commit()
        return chunk_count

    except Exception as e:
        print(f"      ⚠️  DB cleanup failed: {e}")
        return 0
    finally:
        conn.close()


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

    # quarantine list
    p = subparsers.add_parser('quarantine-list', help='List quarantined files')
    p.set_defaults(func=cmd_quarantine_list)

    # quarantine restore
    p = subparsers.add_parser('quarantine-restore', help='Restore file from quarantine')
    p.add_argument('--filename', required=True, help='Quarantined filename (e.g., file.pdf.REJECTED)')
    p.add_argument('--force', action='store_true', help='Overwrite if original path exists')
    p.set_defaults(func=cmd_quarantine_restore)

    # quarantine purge
    p = subparsers.add_parser('quarantine-purge', help='Purge old quarantined files')
    p.add_argument('--days', type=int, default=30, help='Delete files older than N days (default: 30)')
    p.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    p.set_defaults(func=cmd_quarantine_purge)

    # list-incomplete
    p = subparsers.add_parser('list-incomplete', help='List incomplete documents')
    p.add_argument('-l', '--limit', type=int, help='Limit per category')
    p.set_defaults(func=cmd_list_incomplete)

    # reindex-incomplete
    p = subparsers.add_parser('reindex-incomplete', help='Re-index incomplete documents')
    p.add_argument('--dry-run', action='store_true', help='Show what would be re-indexed')
    p.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')
    p.set_defaults(func=cmd_reindex_incomplete)

    # scan-existing
    p = subparsers.add_parser('scan-existing', help='Scan existing files for security issues')
    p.add_argument('--no-quarantine', action='store_true',
                   help='Disable auto-quarantine for CRITICAL files (dry run)')
    p.add_argument('--force-quarantine', action='store_true',
                   help='Also quarantine WARNING files (not recommended)')
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Show all files (including clean ones)')
    p.set_defaults(func=cmd_scan_existing)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
