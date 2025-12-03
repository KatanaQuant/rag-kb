# Troubleshooting Guide

This guide covers general issues that span multiple areas. For topic-specific troubleshooting, see:

- **Build/startup issues**: [QUICK_START.md](QUICK_START.md#troubleshooting)
- **Indexing/search issues**: [USAGE.md](USAGE.md#troubleshooting)
- **Configuration issues**: [CONFIGURATION.md](CONFIGURATION.md#troubleshooting-configuration-issues)
- **MCP integration issues**: [MCP.md](MCP.md#troubleshooting)
- **API/queue issues**: [API.md](API.md#troubleshooting)
- **Database integrity**: [MAINTENANCE.md](MAINTENANCE.md#troubleshooting)
- **Security scanning**: [SECURITY.md](SECURITY.md#troubleshooting)

---

## Service Issues

### Service Won't Start

**Symptom**: `docker-compose up` fails or exits immediately

**Check 1: Port Conflict**
```bash
# Check what's using port 8000
./get-port.sh

# Use different port
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

**Check 2: Docker Resources**
```bash
# Check Docker status
docker info

# Restart Docker daemon (Linux)
sudo systemctl restart docker

# Restart Docker Desktop (macOS/Windows)
```

**Check 3: Container Logs**
```bash
docker-compose logs rag-api
```

Look for error messages indicating missing dependencies, configuration issues, or permission problems.

### Container Keeps Restarting

**Symptom**: Container status shows "Restarting"

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs rag-api --tail 100

# Common causes:
# - Out of memory (increase MAX_MEMORY in .env)
# - Missing dependencies (rebuild: docker-compose build --no-cache)
# - Configuration error (check .env and docker-compose.yml)
```

---

## Docker Issues

### Docker Out of Space

**Symptom**: "no space left on device"

```bash
# Clean up old containers and images
docker system prune -a

# Remove unused volumes
docker volume prune

# Check space
docker system df
```

### Permission Denied Errors

**Symptom**: Can't read/write files in kb/

```bash
# Fix permissions (Linux)
sudo chown -R $USER:$USER kb/ data/

# Or run with sudo (not recommended)
sudo docker-compose up -d
```

### Network Issues

**Symptom**: Can't access on localhost:8000

```bash
# Check if port is bound
netstat -tlnp | grep 8000

# Check Docker network
docker network ls
docker network inspect rag-kb_default

# Try different port
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

---

## Database Issues

### Database Locked

**Symptom**: "Database is locked" errors

```bash
# Stop containers
docker-compose down

# Remove lock files
rm data/*.db-*

# Restart
docker-compose up -d
```

### Database Corruption

**Symptom**: Corruption errors or inconsistent results

```bash
# Stop containers
docker-compose down

# Remove and rebuild database
rm data/rag.db
docker-compose up -d

# Database will be recreated and files reindexed
```

For database integrity issues (orphans, missing chunks), see [MAINTENANCE.md](MAINTENANCE.md).

---

## Performance Issues

### High CPU Usage

**Symptom**: CPU at 100% constantly

```bash
# Check what's running
docker stats rag-api

# Reduce resource limits
echo "MAX_CPUS=2.0" >> .env
docker-compose up --build -d
```

See [CONFIGURATION.md](CONFIGURATION.md#resource-profiles) for tuning profiles.

### High Memory Usage

**Symptom**: System running out of RAM

```bash
# Check memory usage
docker stats rag-api

# Reduce memory limit
echo "MAX_MEMORY=2G" >> .env
docker-compose up --build -d

# Reduce batch size
echo "BATCH_SIZE=3" >> .env
docker-compose restart rag-api
```

---

## Getting Help

If you're still experiencing issues:

1. **Check logs**: `docker-compose logs rag-api --tail 100`
2. **Check health**: `curl http://localhost:8000/health`
3. **Check topic-specific docs**: See links at top of this page
4. **Contact support**: horoshi@katanaquant.com

### Providing Debug Information

When reporting issues, include:

```bash
# System info
uname -a
docker --version
docker-compose --version

# Service health
curl http://localhost:8000/health

# Recent logs
docker-compose logs rag-api --tail 50

# Configuration
cat .env
```
