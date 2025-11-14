# Manual Release Instructions for v0.3.0-alpha

**Date**: 2025-11-14
**Feature**: Automatic File Watching & Real-Time Indexing
**Status**: Ready for Release

---

## Pre-Release Checklist

✅ All tests passing (50+ tests)
✅ Production verified (file watcher working correctly)
✅ Security audit completed (no vulnerabilities)
✅ Documentation updated (README, .env.example)
✅ Code committed (commit: f229dff)
✅ Release notes prepared (RELEASE_v0.3.0-alpha.md)
✅ Agent files updated (.agent/state.md, .agent/history.md)

---

## Release Steps

### 1. Create Git Tag

```bash
cd /media/veracrypt1/CODE/RAG

# Create annotated tag
git tag -a v0.3.0-alpha -m "Release v0.3.0-alpha: Automatic File Watching & Real-Time Indexing"

# Verify tag
git tag -l v0.3.0-alpha
git show v0.3.0-alpha
```

### 2. Push to GitHub

```bash
# Push the commit
git push origin main

# Push the tag
git push origin v0.3.0-alpha
```

### 3. Create GitHub Release

1. Navigate to: https://github.com/KatanaQuant/rag-kb/releases/new

2. **Tag version**: Select `v0.3.0-alpha` from dropdown

3. **Release title**: `v0.3.0-alpha - Automatic File Watching`

4. **Description**: Copy the entire contents from `RELEASE_v0.3.0-alpha.md`

5. **Pre-release**: ✅ Check this box (it's an alpha release)

6. **Set as latest release**: ✅ Check this box

7. Click **Publish release**

---

## Post-Release Verification

### Verify Release Page
- [ ] Release appears at: https://github.com/KatanaQuant/rag-kb/releases/tag/v0.3.0-alpha
- [ ] Release notes are complete and formatted correctly
- [ ] "Pre-release" badge is visible
- [ ] Download links work (Source code zip/tar.gz)

### Verify Installation
```bash
# Test fresh clone and checkout
cd /tmp
git clone https://github.com/KatanaQuant/rag-kb.git test-install
cd test-install
git checkout v0.3.0-alpha
docker-compose up -d

# Wait for startup
sleep 30

# Verify health
curl http://localhost:8000/health

# Check logs for watcher
docker-compose logs rag-api | grep "File watcher"

# Cleanup
docker-compose down
cd ..
rm -rf test-install
```

---

## Update Repository State

After successful release:

```bash
cd /media/veracrypt1/CODE/RAG

# Update state.md
# Change "Latest Commit: Pending" to "Latest Commit: f229dff"
# Change "Version: v0.3.0-alpha (ready for release)" to "Version: v0.3.0-alpha"
```

---

## Announcement Template

Optional: Post to relevant channels

**Subject**: RAG-KB v0.3.0-alpha Released - Automatic File Watching

**Message**:
```
RAG-KB v0.3.0-alpha is now available!

Key Feature: Automatic File Watching & Real-Time Indexing

Drop files into knowledge_base/ and they're automatically indexed within 10 seconds - no restart needed!

Features:
✅ Smart debouncing for bulk operations
✅ Thread-safe event handling
✅ Fully configurable (debounce time, batch size)
✅ Production tested and verified

Download: https://github.com/KatanaQuant/rag-kb/releases/tag/v0.3.0-alpha
Documentation: https://github.com/KatanaQuant/rag-kb#auto-sync-configuration
```

---

## Rollback Procedure

If critical issues are found post-release:

```bash
# Delete the tag locally
git tag -d v0.3.0-alpha

# Delete the tag remotely
git push origin :refs/tags/v0.3.0-alpha

# Delete the GitHub release (via web interface)

# Revert the commit if needed
git revert f229dff
git push origin main
```

---

## Next Steps

After release:
1. Monitor GitHub issues for bug reports
2. Monitor discussions for feedback
3. Update .agent/state.md with final commit reference
4. Plan next feature based on user feedback

---

**Release Ready!** Execute steps 1-3 above to publish v0.3.0-alpha to GitHub.
