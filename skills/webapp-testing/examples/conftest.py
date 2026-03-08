"""
Pytest fixtures for web application testing with Playwright.

Copy this file to your project's tests/ directory and customize as needed.
Provides automatic evidence collection, base URL discovery, and failure handling.

Usage:
    1. Copy to tests/conftest.py
    2. Ensure runtime.json exists (created by server_manager.py)
    3. Run tests with: python run_test.py --path tests/
"""

import json
import os
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Page, BrowserContext, Browser, Playwright


RUNTIME_FILE = ".verdent/testing/runtime.json"
EVIDENCE_TEMP_DIR = os.environ.get("EVIDENCE_TEMP_DIR", "/tmp/playwright-evidence")


def load_runtime() -> dict:
    if os.path.exists(RUNTIME_FILE):
        with open(RUNTIME_FILE) as f:
            return json.load(f)
    return {"services": {}}


@pytest.fixture(scope="session")
def base_url() -> str:
    """
    Get base URL from environment or runtime.json.
    
    Priority:
    1. BASE_URL environment variable
    2. TEST_SERVICE env var specifies which service (default: frontend)
    3. First available service in runtime.json
    4. Fallback to http://localhost:3000
    """
    if url := os.environ.get("BASE_URL"):
        return url
    
    runtime = load_runtime()
    services = runtime.get("services", {})
    
    service_name = os.environ.get("TEST_SERVICE", "frontend")
    if service_name in services:
        return services[service_name].get("url", "http://localhost:3000")
    
    if services:
        first_service = next(iter(services.values()))
        return first_service.get("url", "http://localhost:3000")
    
    return "http://localhost:3000"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Configure browser context with viewport and other settings."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture
def evidence_recorder(request, page: Page) -> Generator[dict, None, None]:
    """
    Record console and network events during test execution.
    
    Yields a dict containing collected logs that can be inspected during test.
    Automatically saves to files after test completion.
    """
    console_logs = []
    network_logs = []
    
    def on_console(msg):
        entry = {
            "level": msg.type,
            "text": msg.text,
            "url": msg.location.get("url", "") if hasattr(msg, "location") else "",
            "line": msg.location.get("lineNumber", 0) if hasattr(msg, "location") else 0,
        }
        console_logs.append(entry)
        
        if msg.type in ["error", "warning"]:
            print(f"[CONSOLE {msg.type.upper()}] {msg.text[:200]}")
    
    def on_request_failed(request):
        network_logs.append({
            "type": "failed",
            "method": request.method,
            "url": request.url,
            "failure": request.failure,
        })
    
    def on_response(response):
        timing = {}
        try:
            timing = response.timing or {}
        except Exception:
            pass
        
        duration_ms = timing.get("responseEnd", 0)
        
        if response.status >= 400 or duration_ms > 3000:
            network_logs.append({
                "type": "slow" if duration_ms > 3000 else "error",
                "method": response.request.method,
                "url": response.url,
                "status": response.status,
                "duration_ms": duration_ms,
            })
    
    page.on("console", on_console)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    
    evidence = {"console": console_logs, "network": network_logs}
    yield evidence
    
    Path(EVIDENCE_TEMP_DIR).mkdir(parents=True, exist_ok=True)
    test_name = request.node.name
    
    with open(os.path.join(EVIDENCE_TEMP_DIR, f"{test_name}_console.json"), "w") as f:
        json.dump(console_logs, f, indent=2)
    
    with open(os.path.join(EVIDENCE_TEMP_DIR, f"{test_name}_network.json"), "w") as f:
        json.dump(network_logs, f, indent=2)


@pytest.fixture
def api_client(base_url: str):
    """
    HTTP client for API testing (no browser needed).
    
    Requires httpx: pip install httpx
    """
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed - required for API tests")
    
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Capture screenshot and DOM snapshot on test failure.
    
    This hook runs after each test phase (setup, call, teardown).
    On failure during the 'call' phase, it captures evidence.
    """
    outcome = yield
    report = outcome.get_result()
    
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page and hasattr(page, "screenshot"):
            Path(EVIDENCE_TEMP_DIR).mkdir(parents=True, exist_ok=True)
            test_name = item.name
            
            try:
                screenshot_path = os.path.join(EVIDENCE_TEMP_DIR, f"{test_name}_failure.png")
                page.screenshot(path=screenshot_path, full_page=True)
            except Exception as e:
                print(f"Failed to capture screenshot: {e}")
            
            try:
                dom_path = os.path.join(EVIDENCE_TEMP_DIR, f"{test_name}_dom.html")
                with open(dom_path, "w") as f:
                    f.write(page.content())
            except Exception as e:
                print(f"Failed to capture DOM: {e}")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "smoke: mark test as smoke test")
    config.addinivalue_line("markers", "regression: mark test as regression test")
    config.addinivalue_line("markers", "ui: mark test as UI/browser test")
    config.addinivalue_line("markers", "api: mark test as API test")
    config.addinivalue_line("markers", "slow: mark test as slow-running")
