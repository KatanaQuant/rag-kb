# Advanced Malware Detection Setup

## Overview

RAG-KB includes three layers of malware detection for the knowledge base:

1. **ClamAV Integration** - Virus signature scanning using ClamAV daemon
2. **Hash Blacklist** - SHA256 hash checking against known malware database
3. **YARA Rules** - Custom pattern matching for suspicious content

All three are **enabled by default** and can be disabled independently via environment variables.

## Quick Start

All malware detection features are **enabled by default** for maximum security:

```yaml
# docker-compose.yml
services:
  rag-api:
    environment:
      # Enable ClamAV virus scanning
      CLAMAV_ENABLED: "true"
      CLAMAV_SOCKET: "/var/run/clamav/clamd.ctl"

      # Enable hash blacklist
      HASH_BLACKLIST_ENABLED: "true"
      HASH_BLACKLIST_PATH: "/app/data/malware_hashes.txt"

      # Enable YARA rules
      YARA_ENABLED: "true"
      YARA_RULES_PATH: "/app/yara_config/yara_rules.yar"
```

## 1. ClamAV Integration

### What It Does
Scans files for virus signatures using ClamAV's extensive malware database.

### Setup

**Option A: Install ClamAV in Container**

```dockerfile
# Add to Dockerfile
RUN apt-get update && apt-get install -y \
    clamav \
    clamav-daemon \
    && rm -rf /var/lib/apt/lists/*

# Update virus definitions
RUN freshclam
```

```yaml
# docker-compose.yml
services:
  rag-api:
    environment:
      CLAMAV_ENABLED: "true"
      CLAMAV_SOCKET: "/var/run/clamav/clamd.ctl"
    volumes:
      - clamav_data:/var/lib/clamav
```

**Option B: Use Separate ClamAV Container**

```yaml
# docker-compose.yml
services:
  clamav:
    image: clamav/clamav:latest
    container_name: clamav
    volumes:
      - clamav_data:/var/lib/clamav
    ports:
      - "3310:3310"

  rag-api:
    environment:
      CLAMAV_ENABLED: "true"
      CLAMAV_SOCKET: "clamav:3310"  # Use TCP instead of socket
    depends_on:
      - clamav
```

### Verification

```bash
# Test ClamAV is running
docker-compose exec rag-api clamdscan --version

# Scan a test file
docker-compose exec rag-api clamdscan /app/kb/test.pdf
```

### Dependencies

```bash
pip install clamd
```

Already included in `requirements.txt`.

## 2. Hash Blacklist

### What It Does
Checks file SHA256 hashes against a database of known malware.

### Setup

1. **Edit the blacklist file:**
   ```bash
   vim data/malware_hashes.txt
   ```

2. **Add known malware hashes (one per line):**
   ```
   # Example malware hashes
   d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2
   e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3
   ```

3. **Enable in docker-compose.yml:**
   ```yaml
   environment:
     HASH_BLACKLIST_ENABLED: "true"
     HASH_BLACKLIST_PATH: "/app/data/malware_hashes.txt"
   ```

### Hash Sources

**Free Malware Hash Databases:**
- [MalwareBazaar](https://bazaar.abuse.ch/) - Community malware repository
- [VirusTotal](https://www.virustotal.com/) - Scan files and get hashes
- [Hybrid Analysis](https://www.hybrid-analysis.com/) - Malware analysis
- [URLhaus](https://urlhaus.abuse.ch/) - Malicious URLs and payloads

**Updating the Blacklist:**

```bash
# Download MalwareBazaar recent hashes (example)
curl -X POST https://mb-api.abuse.ch/api/v1/ \
  -d "query=get_recent" \
  | jq -r '.data[].sha256_hash' \
  >> data/malware_hashes.txt

# Remove duplicates
sort -u data/malware_hashes.txt -o data/malware_hashes.txt
```

### No Dependencies
Uses Python's built-in `hashlib` library.

## 3. YARA Rules

### What It Does
Detects suspicious patterns in files using custom YARA rules.

### Setup

1. **Install YARA in container:**
   ```dockerfile
   # Add to Dockerfile
   RUN apt-get update && apt-get install -y \
       yara \
       python3-yara \
       && rm -rf /var/lib/apt/lists/*
   ```

2. **Edit YARA rules:**
   ```bash
   vim config/yara_rules.yar
   ```

   Sample rules are provided in `config/yara_rules.yar`:
   - Embedded executables
   - Suspicious VBA macros
   - Malicious PDF JavaScript
   - Shellcode patterns
   - Archive bombs

3. **Enable in docker-compose.yml:**
   ```yaml
   environment:
     YARA_ENABLED: "true"
     YARA_RULES_PATH: "/app/config/yara_rules.yar"
   ```

### Custom Rules

Add your own rules to `config/yara_rules.yar`:

```yara
rule My_Custom_Rule {
    meta:
        description = "Custom malware detection"
        author = "Your Name"
        severity = "high"

    strings:
        $pattern1 = "suspicious_string"
        $pattern2 = { AB CD EF }  // Hex pattern

    condition:
        any of them
}
```

### YARA Resources
- [Official YARA Documentation](https://yara.readthedocs.io/)
- [Awesome YARA](https://github.com/InQuest/awesome-yara) - Curated rules
- [YARA Rules Repository](https://github.com/Yara-Rules/rules)

### Dependencies

```bash
pip install yara-python
```

Already included in `requirements.txt`.

## Validation Chain

Files are validated in this order:

1. File existence check
2. File size limits (500 MB default)
3. Extension validation
4. Executable permission check
5. Extension/content mismatch detection
6. Archive bomb detection
7. **Advanced malware detection (Phase 3):**
   - ClamAV scan (if enabled)
   - Hash blacklist check (if enabled)
   - YARA rules scan (if enabled)
8. Magic byte signature validation

If any check fails, the file is **rejected** and:
- Tracked in database (`processing_progress` table)
- Quarantined (if dangerous: executables, zip bombs, scripts)
- Logged with rejection reason

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAMAV_ENABLED` | `true` | Enable ClamAV virus scanning |
| `CLAMAV_SOCKET` | `/var/run/clamav/clamd.ctl` | ClamAV socket or host:port |
| `HASH_BLACKLIST_ENABLED` | `true` | Enable hash blacklist checking |
| `HASH_BLACKLIST_PATH` | `/app/data/malware_hashes.txt` | Path to hash blacklist file |
| `YARA_ENABLED` | `true` | Enable YARA pattern matching |
| `YARA_RULES_PATH` | `/app/yara_config/yara_rules.yar` | Path to YARA rules file |

### Config Object

```python
from config import default_config

# Access malware detection config
config = default_config.malware_detection

print(config.clamav_enabled)
print(config.hash_blacklist_path)
print(config.yara_enabled)
```

## Performance Considerations

### ClamAV
- **Slowest** - Full signature scanning
- Adds ~100-500ms per file
- CPU-intensive
- Use for high-security environments

### Hash Blacklist
- **Fastest** - SHA256 lookup only
- Adds ~1-5ms per file
- Memory-efficient (hashes loaded once)
- Recommended for all environments

### YARA
- **Medium** - Pattern matching
- Adds ~50-200ms per file
- Speed depends on rule complexity
- Use for targeted threat detection

### Recommendations

**Low-security (speed priority):**
```yaml
HASH_BLACKLIST_ENABLED: "true"
CLAMAV_ENABLED: "false"
YARA_ENABLED: "false"
```

**Balanced (recommended):**
```yaml
HASH_BLACKLIST_ENABLED: "true"
CLAMAV_ENABLED: "false"
YARA_ENABLED: "true"
```

**High-security (thorough scanning):**
```yaml
HASH_BLACKLIST_ENABLED: "true"
CLAMAV_ENABLED: "true"
YARA_ENABLED: "true"
```

## Testing

### Unit Tests

```bash
# Run malware detection tests
docker-compose exec rag-api pytest tests/test_malware_detection.py -v
```

### Manual Testing

**Test hash blacklist:**
```bash
# Add test file hash to blacklist
sha256sum kb/test.pdf >> data/malware_hashes.txt

# Try to index it (should be rejected)
curl -X POST "http://localhost:8000/api/index?path=test.pdf&force=true"
```

**Test ClamAV:**
```bash
# Download EICAR test file (harmless malware test)
curl -o kb/eicar.txt https://secure.eicar.org/eicar.com.txt

# Try to index it (should be rejected)
curl -X POST "http://localhost:8000/api/index?path=eicar.txt&force=true"
```

**Test YARA:**
```bash
# Create file with suspicious pattern
echo "MZ" > kb/suspicious.bin

# Try to index it (should be rejected by Suspicious_Embedded_Executable rule)
curl -X POST "http://localhost:8000/api/index?path=suspicious.bin&force=true"
```

## Troubleshooting

### ClamAV Not Working

**Check ClamAV is running:**
```bash
docker-compose exec rag-api ps aux | grep clam
```

**Check socket exists:**
```bash
docker-compose exec rag-api ls -l /var/run/clamav/clamd.ctl
```

**Check logs:**
```bash
docker-compose exec rag-api tail -f /var/log/clamav/clamd.log
```

**Update virus definitions:**
```bash
docker-compose exec rag-api freshclam
```

### YARA Rules Not Loading

**Check syntax:**
```bash
docker-compose exec rag-api yara -w config/yara_rules.yar
```

**Check file exists:**
```bash
docker-compose exec rag-api ls -l /app/config/yara_rules.yar
```

### Hash Blacklist Not Working

**Check file format:**
```bash
# Hashes must be lowercase, 64 hex chars
cat data/malware_hashes.txt | grep -v '^#' | head
```

**Verify hash calculation:**
```bash
sha256sum kb/test.pdf
```

## Security Best Practices

1. **Update regularly:**
   - ClamAV signatures: Run `freshclam` daily
   - Hash blacklist: Update from threat feeds weekly
   - YARA rules: Review and update monthly

2. **Layered defense:**
   - Enable multiple detection methods
   - Don't rely on a single strategy

3. **Monitor rejections:**
   ```bash
   curl http://localhost:8000/api/security/rejected
   ```

4. **Audit quarantined files:**
   ```bash
   curl http://localhost:8000/api/security/quarantine
   ```

5. **Test your setup:**
   - Use EICAR test file for ClamAV
   - Add test hashes to blacklist
   - Create test files matching YARA rules

## Files Modified (Phase 3)

```
CREATED:
  api/ingestion/malware_detection.py          # ClamAV, hash, YARA strategies
  config/yara_rules.yar                       # Sample YARA rules
  data/malware_hashes.txt                     # Sample hash blacklist
  MALWARE_DETECTION_SETUP.md                  # This file

MODIFIED:
  api/config.py                               # Added MalwareDetectionConfig
  api/environment_config_loader.py            # Load malware config from env
  api/ingestion/file_type_validator.py        # Integrated AdvancedMalwareDetector
```

## Completed

All security features are implemented and available via REST API:

1. **Malware detection** - ClamAV, YARA, hash blacklist (v1.5.0)
2. **Security REST API** - All management via `/api/security/*` endpoints (v1.6.0)
3. **Parallel scanning** - ThreadPoolExecutor with 8 workers (v1.6.0)

## References

- [ClamAV Documentation](https://docs.clamav.net/)
- [YARA Documentation](https://yara.readthedocs.io/)
- [MalwareBazaar](https://bazaar.abuse.ch/)
