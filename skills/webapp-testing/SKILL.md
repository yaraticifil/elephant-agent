---
name: webapp-testing
description: >
  Universal web application testing toolkit. Supports service lifecycle management
  (start/restart/reload/health-check), Playwright UI tests and API/WS validation,
  failure evidence collection (trace/screenshot/logs/network), and structured issue
  reports. Designed for Agent-driven test-debug-fix-regression loops.
---

# Web Application Testing

A comprehensive toolkit for automated web application testing with Playwright.

**Core Scripts** (always run `--help` first):

- `scripts/server_manager.py` - Service lifecycle management
- `scripts/run_test.py` - Test execution with structured output
- `scripts/collect_evidence.py` - Evidence organization and archival
- `scripts/report_issue.py` - Structured issue report generation

## Decision Tree

```
Task → Is it a UI test or API test?
    │
    ├─ UI Test → Is the frontend server running?
    │   ├─ No → server_manager.py start --name frontend
    │   └─ Yes → run_test.py --suite ui
    │
    └─ API Test → Is the backend server running?
        ├─ No → server_manager.py start --name backend
        └─ Yes → run_test.py --suite api
```

## Quick Start

### 1. Start Services

```bash
# Single service with auto port detection
python3 scripts/server_manager.py start \
  --service "npm run dev" --name frontend --port auto

# Multiple services
python3 scripts/server_manager.py start \
  --service "npm run dev" --name frontend --port auto \
  --service "python3 app/main.py" --name backend --port auto
```

### 2. Run Tests

```bash
# Run smoke tests
python3 scripts/run_test.py --suite smoke

# Run specific test file
python3 scripts/run_test.py --path tests/e2e/test_login.py

# Rerun only failed tests
python3 scripts/run_test.py --rerun-failed
```

### 3. After Code Changes

```bash
# Frontend changes (HMR): just wait for ready
python3 scripts/server_manager.py wait-ready --name frontend

# Backend changes: restart required
python3 scripts/server_manager.py restart --name backend

# Then rerun failed tests
python3 scripts/run_test.py --rerun-failed
```

### 4. View Results

Test results are output as JSON to stdout for Agent parsing:

```json
{
  "status": "failed",
  "summary": { "total": 10, "passed": 8, "failed": 2 },
  "failures": [
    {
      "name": "test_login_success",
      "error_message": "Expected 'Dashboard' in title",
      "evidence_dir": ".verdent/testing/evidence/run_20260121_143022/test_login_success/"
    }
  ]
}
```

## Service Manager Commands

| Command      | Purpose                                                   |
| ------------ | --------------------------------------------------------- |
| `start`      | Start services, wait for health check, write runtime.json |
| `stop`       | Graceful shutdown (SIGTERM → SIGKILL after timeout)       |
| `restart`    | Stop + start a specific service                           |
| `reload`     | Call project's reload API without restarting process      |
| `wait-ready` | Wait for health check only (useful after HMR)             |
| `status`     | Output current service status as JSON                     |
| `logs`       | View service logs (tail/full/time-range)                  |

### Port Discovery Modes

```bash
--port 8000           # Fixed port
--port auto           # Parse from stdout JSON {"port": N}
--port-file /tmp/p    # Read from file
```

### Health Check Options

```bash
--health-check tcp                              # TCP port connect (default)
--health-check "http://localhost:PORT/health"   # HTTP 200 check
--health-check "curl -s localhost:PORT/ready"   # Custom command
```

## Evidence Collection

On test failure, evidence is automatically collected:

| Type       | Source               | Format                              |
| ---------- | -------------------- | ----------------------------------- |
| Trace      | Playwright tracing   | .zip (view at trace.playwright.dev) |
| Screenshot | page.screenshot()    | .png (full page on failure)         |
| Video      | Context recording    | .webm (if enabled)                  |
| Console    | page.on('console')   | .json (grouped by level)            |
| Network    | page.on('response')  | .json (failed/4xx/5xx/slow)         |
| DOM        | page.content()       | .html snapshot                      |
| Logs       | Server stdout/stderr | .log (time-range filtered)          |

Evidence directory structure:

```
.verdent/testing/evidence/run_<timestamp>/
├── evidence_index.json
└── <test_name>/
    ├── trace.zip
    ├── failure_screenshot.png
    ├── console.json
    ├── network.json
    ├── dom_snapshot.html
    └── backend.log
```

## Issue Reports

Generated at `.verdent/testing/issues/<timestamp>_<test_name>.md`:

- Environment info (git commit, branch, services, ports)
- Reproduction steps (auto-extracted from trace)
- Expected vs Actual
- Error stack trace
- Key log summaries (console errors, failed requests)
- Evidence file links
- Fix description (Agent fills)
- Regression result (Agent fills)

## Runtime Files

### runtime.json

Written by `server_manager.py start`, read by `run_test.py`:

```json
{
  "services": {
    "frontend": {
      "pid": 12345,
      "port": 5173,
      "url": "http://localhost:5173",
      "log_file": ".verdent/testing/logs/frontend.log"
    }
  }
}
```

## Agent Loop Example

```
iteration = 0
max_iterations = 5

while iteration < max_iterations:
    result = run_test.py --suite smoke
    if result.status == "passed":
        break

    # Analyze failures using evidence
    analyze(result.failures, result.evidence_base)

    # Fix code
    fix_code(...)

    # Update services based on what changed
    if modified_frontend:
        server_manager.py wait-ready --name frontend
    if modified_backend:
        server_manager.py restart --name backend

    iteration += 1

if iteration == max_iterations:
    report_issue.py --test-name ... --evidence-dir ...
```

## Best Practices

1. **Always wait for networkidle** before inspecting dynamic pages
2. **Use `--rerun-failed`** after fixes instead of full suite
3. **Check runtime.json** if base_url seems wrong
4. **Enable video only when needed** (`--video retain-on-failure`) to save disk
5. **Use descriptive markers** (`@pytest.mark.smoke`, `@pytest.mark.api`) for filtering

## Common Pitfalls

- **Port already in use**: Run `server_manager.py stop` first
- **Stale runtime.json**: Delete `.verdent/testing/runtime.json` if services were killed externally
- **Missing dependencies**: Core requires only `pytest` + `playwright`; optional plugins enhance but are not required

## Security Note

`server_manager.py` uses `shell=True` when executing service commands. This is intentional to support shell features like pipes and environment variables. However:

- **Never pass untrusted input** to `--service` parameter
- If integrating with user-provided commands, validate and sanitize inputs first
- Consider using `shlex.quote()` for any dynamic command components

## Environment Setup

### macOS (Required: Shared Virtual Environment)

macOS system Python is externally managed and does not allow `pip install` directly. Use a shared virtual environment to avoid repeated installations across projects:

```bash
# One-time setup: create shared testing environment
python3 -m venv ~/.verdent/skills/webapp-testing/.venv
source ~/.verdent/skills/webapp-testing/.venv/bin/activate
pip install playwright pytest pytest-playwright httpx psutil
playwright install chromium
```

```bash
# For any project: just activate and use
source ~/.verdent/skills/webapp-testing/.venv/bin/activate
cd /path/to/your/project
python3 run_test.py --path tests/e2e/
```

**Agent Note**: If you encounter `externally-managed-environment` error, do NOT retry `pip install`. Instead:

1. Check if shared venv exists: `ls ~/.verdent/skills/webapp-testing/.venv`
2. If exists → activate it: `source ~/.verdent/skills/webapp-testing/.venv/bin/activate`
3. If not exists → create it with commands above
4. Then retry within the activated environment

### Linux (Shared Virtual Environment)

Use a shared virtual environment to avoid repeated installations:

```bash
# One-time setup
python3 -m venv ~/.verdent/skills/webapp-testing/.venv
source ~/.verdent/skills/webapp-testing/.venv/bin/activate
pip install playwright pytest pytest-playwright httpx psutil
playwright install chromium
```

```bash
# For any project: just activate and use
source ~/.verdent/skills/webapp-testing/.venv/bin/activate
cd /path/to/your/project
python3 run_test.py --path tests/e2e/
```

**Agent Note (Linux)**: If `pip install` fails:

1. Check if shared venv exists: `ls ~/.verdent/skills/webapp-testing/.venv`
2. If exists → activate: `source ~/.verdent/skills/webapp-testing/.venv/bin/activate`
3. If not exists → create with commands above

### Windows (Shared Virtual Environment)

**System Requirements**: Windows 11+, Windows Server 2019+, or WSL.

```powershell
# One-time setup (PowerShell)
python -m venv $HOME\.verdent\skills\webapp-testing\.venv
& $HOME\.verdent\skills\webapp-testing\.venv\Scripts\Activate.ps1
pip install playwright pytest pytest-playwright httpx psutil
playwright install chromium
```

```powershell
# For any project: just activate and use
& $HOME\.verdent\skills\webapp-testing\.venv\Scripts\Activate.ps1
cd C:\path\to\your\project
python run_test.py --path tests\e2e\
```

**Windows-Specific Notes**:

1. **Use `python` not `python3`** - Windows typically uses `python` command
2. **PowerShell execution policy** - If `.ps1` script blocked, run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. **Service commands may differ** - `server_manager.py` uses `shell=True` which invokes `cmd.exe`. Some Unix commands (e.g., `curl`, `grep`) may not work. Use PowerShell equivalents or install via [Git Bash](https://git-scm.com/download/win).
4. **Path separators** - Use backslashes `\` or raw strings in Python paths

**Agent Note (Windows)**: If `pip` fails with permission error:

1. Check if shared venv exists: `Test-Path $HOME\.verdent\skills\webapp-testing\.venv`
2. If exists → activate: `& $HOME\.verdent\skills\webapp-testing\.venv\Scripts\Activate.ps1`
3. If not exists → create with commands above
4. Do NOT run as Administrator for pip

### Verify Environment

```bash
# macOS / Linux
which python3   # Should show ~/.verdent/skills/webapp-testing/.venv/bin/python3
python3 -c "import playwright; import pytest; print('OK')"
```

```powershell
# Windows (PowerShell)
Get-Command python   # Should show $HOME\.verdent\skills\webapp-testing\.venv\Scripts\python.exe
python -c "import playwright; import pytest; print('OK')"
```

### Project Integration

For non-Python projects using this testing toolkit, add the following to `.gitignore`:

```gitignore
# Python artifacts (shared venv is outside project, but these may still appear)
__pycache__/
*.pyc
.pytest_cache/
htmlcov/

# Testing runtime
.verdent/testing/evidence/
.verdent/testing/logs/
.verdent/testing/runtime.json
```

**Recommended test directory structure:**

```
project/
├── src/                      # Your project code (any language)
├── tests/
│   ├── e2e/                  # Playwright E2E tests (Python)
│   │   ├── conftest.py
│   │   └── test_*.py
│   └── unit/                 # Unit tests (project's language)
├── .venv/                    # Python venv (gitignored)
└── .verdent/testing/         # Runtime artifacts (gitignored)
```

## Dependencies

**Required:**

```
playwright>=1.40.0
pytest>=8.0.0
pytest-playwright>=0.4.0
httpx>=0.25.0
```

**Optional (auto-detected):**

```
pytest-xdist        # Parallel execution
pytest-html         # HTML reports
pytest-json-report  # JSON reports
psutil              # Process tree management
```

**System:**

```bash
playwright install chromium
```
