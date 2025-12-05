#!/usr/bin/env python3
"""Rebuild FTS index with correct rowid mapping."""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else '/app/data/rag.db'

conn = sqlite3.connect(db_path)

print('=== FTS Rebuild with correct rowid ===')

# Step 1: Drop old FTS table
print('1. Dropping old FTS table...')
conn.execute('DROP TABLE IF EXISTS fts_chunks')
conn.commit()

# Step 2: Create new FTS table
print('2. Creating new FTS table...')
conn.execute('''
    CREATE VIRTUAL TABLE fts_chunks USING fts5(
        chunk_id UNINDEXED,
        content,
        content='',
        contentless_delete=1
    )
''')
conn.commit()

# Step 3: Populate with explicit rowid = chunk_id
print('3. Populating FTS from chunks...')
cursor = conn.execute('SELECT id, content FROM chunks ORDER BY id')
batch = []
count = 0
for chunk_id, content in cursor:
    batch.append((chunk_id, chunk_id, content))
    if len(batch) >= 1000:
        conn.executemany('INSERT INTO fts_chunks(rowid, chunk_id, content) VALUES (?, ?, ?)', batch)
        conn.commit()
        count += len(batch)
        if count % 10000 == 0:
            print(f'   Inserted {count} rows...')
        batch = []

if batch:
    conn.executemany('INSERT INTO fts_chunks(rowid, chunk_id, content) VALUES (?, ?, ?)', batch)
    conn.commit()
    count += len(batch)

print(f'4. Total rows inserted: {count}')

# Force WAL checkpoint
print('5. Forcing WAL checkpoint...')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.commit()

# Verify
print('6. Verification...')
test = conn.execute('SELECT rowid FROM fts_chunks WHERE fts_chunks MATCH "tidy" LIMIT 5').fetchall()
print(f'   FTS search "tidy": {[r[0] for r in test]}')

conn.close()
print('=== FTS Rebuild Complete ===')
