# Docker Testing Guide

This directory contains Docker configurations for testing Scrappy across different platforms, particularly Linux.

## Quick Start

### Prerequisites
- Docker installed
- Docker Compose installed

### Running Tests

**Linux/Mac:**
```bash
# Make script executable (first time only)
chmod +x docker-test.sh

# Run all tests
./docker-test.sh all

# Run specific tests
./docker-test.sh semantic
./docker-test.sh demo
```

**Windows (PowerShell):**
```powershell
# Run all tests
.\docker-test.ps1 all

# Run specific tests
.\docker-test.ps1 semantic
.\docker-test.ps1 demo
```

## Available Commands

### Test Commands

| Command | Description |
|---------|-------------|
| `all` | Run full test suite (default) |
| `semantic` | Run semantic search fixture tests only |
| `demo` | Run integration demo with progress display |
| `demo-semantic` | Run semantic search POC |
| `shell` | Open interactive bash shell in container |
| `build` | Build Docker image |
| `clean` | Remove containers and volumes |

### Manual Docker Compose

You can also use docker-compose directly:

```bash
# Run all tests
docker-compose run --rm test

# Run semantic tests
docker-compose run --rm test-semantic

# Run integration demo
docker-compose run --rm demo

# Open shell for debugging
docker-compose run --rm scrappy bash

# Clean up
docker-compose down -v
```

## Architecture

### Services

**scrappy** - Development environment with bash shell
- Full environment with mounted source code
- Use for interactive development and debugging

**test** - Run full test suite
- Runs `pytest tests/ -v --tb=short`
- Fast tests (no semantic search loading)

**test-semantic** - Run semantic search tests
- Runs `pytest tests/test_semantic_fixtures.py -v`
- Tests mock fixtures work correctly

**demo** - Run integration demo
- Shows CLI progress display during startup
- Demonstrates semantic search initialization

**demo-semantic** - Run semantic search POC
- Creates temp directory with test files
- Indexes and searches with real FastEmbed/LanceDB

### Volumes

**scrappy-data** - Persisted data directory
- Stores `.scrappy/` directory between runs
- Contains LanceDB databases
- Persists across container restarts

**Source mounts** - Live code editing
- `./src` → `/app/src`
- `./tests` → `/app/tests`
- `./scripts` → `/app/scripts`
- Changes on host are immediately reflected in container

## Testing Workflow

### 1. Initial Build
```bash
./docker-test.sh build
```

### 2. Run Quick Tests (Fast)
```bash
# Should complete in ~1-2 seconds
./docker-test.sh semantic
```

### 3. Run Integration Demo (Slow)
```bash
# First run loads FastEmbed model (10-30s)
# Creates database in .scrappy/lancedb/
./docker-test.sh demo
```

### 4. Verify Database Created
```bash
# Open shell and check
./docker-test.sh shell

# Inside container:
ls -la .scrappy/lancedb/
```

### 5. Full Test Suite
```bash
# Should be fast (~80-90s) - no real model loading
./docker-test.sh all
```

## Platform-Specific Testing

### Linux Differences
- File permissions (user ID 1000)
- Path separators (forward slashes)
- Temp directory locations
- Git behavior

### Windows Differences
- Line endings (CRLF vs LF)
- Path handling (backslashes)
- Case-sensitive file systems

### Docker Benefits
- Consistent Linux environment regardless of host OS
- Reproducible test results
- Isolated from host system dependencies
- Easy cleanup with volumes

## Troubleshooting

### Tests are slow
```bash
# Clean volumes and rebuild
./docker-test.sh clean
./docker-test.sh build
```

### Permission errors
```bash
# Container runs as user ID 1000
# Check volume permissions
docker-compose run --rm scrappy ls -la .scrappy/
```

### Database not created
```bash
# Check if semantic search is enabled
docker-compose run --rm scrappy bash
# Inside container:
python -c "from src.orchestrator import AgentOrchestrator; o = AgentOrchestrator(enable_semantic_search=True); print(o.enable_semantic_search)"
```

### Out of disk space
```bash
# Remove unused Docker resources
docker system prune -a
```

## Development Tips

### Interactive Development
```bash
# Open shell in container
./docker-test.sh shell

# Run tests manually
pytest tests/test_semantic_fixtures.py -v

# Run demos
python scripts/demo_integration.py

# Check logs
ls -la .scrappy/
```

### Debugging
```bash
# Run with verbose output
docker-compose run --rm test python -m pytest tests/ -vv

# Run specific test
docker-compose run --rm test python -m pytest tests/test_semantic_fixtures.py::test_mock_semantic_search_basic -vv

# Check environment
docker-compose run --rm scrappy env
```

### Performance Comparison
```bash
# Time test execution
time ./docker-test.sh semantic

# Compare with host
time python -m pytest tests/test_semantic_fixtures.py -v
```

## CI/CD Integration

The Docker setup is ready for CI/CD:

```yaml
# Example GitHub Actions
- name: Run tests in Docker
  run: |
    docker-compose run --rm test

- name: Run semantic tests
  run: |
    docker-compose run --rm test-semantic
```

## Notes

- First build may take 5-10 minutes (downloads base image, installs deps)
- Subsequent builds are fast (uses cache)
- FastEmbed model downloads once per volume
- Tests should be platform-agnostic with Docker
