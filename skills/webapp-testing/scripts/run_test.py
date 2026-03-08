#!/usr/bin/env python3
"""
Test execution wrapper with structured JSON output for Agent consumption.

Runs pytest with Playwright, collects evidence on failure, and outputs
structured results suitable for automated analysis.

Usage:
    python run_test.py --path tests/e2e/
    python run_test.py --suite smoke
    python run_test.py --rerun-failed
    python run_test.py --path tests/ --parallel 4 --max-failures 3
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional


RUNTIME_FILE = ".verdent/testing/runtime.json"
REPORTS_DIR = ".verdent/testing/reports"
EVIDENCE_DIR = ".verdent/testing/evidence"
LAST_FAILED_FILE = ".verdent/testing/.last_failed.json"


def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs():
    Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)


def load_runtime() -> dict:
    if os.path.exists(RUNTIME_FILE):
        with open(RUNTIME_FILE) as f:
            return json.load(f)
    return {"services": {}}


def get_base_url(service_name: str = "frontend") -> Optional[str]:
    runtime = load_runtime()
    services = runtime.get("services", {})
    if service_name in services:
        return services[service_name].get("url")
    if services:
        first = next(iter(services.values()))
        return first.get("url")
    return None


def detect_plugins() -> list:
    plugins = []
    
    plugin_import_map = {
        "pytest-json-report": "pytest_jsonreport",
        "pytest-html": "pytest_html",
        "pytest-xdist": "xdist",
        "pytest-rerunfailures": "pytest_rerunfailures",
        "pytest-playwright": "pytest_playwright",
    }
    
    for pkg_name, import_name in plugin_import_map.items():
        try:
            __import__(import_name)
            plugins.append(pkg_name)
        except ImportError:
            pass
    
    return plugins


def build_pytest_args(
    path: Optional[str] = None,
    suite: Optional[str] = None,
    filter_expr: Optional[str] = None,
    rerun_failed: bool = False,
    max_failures: Optional[int] = None,
    parallel: int = 1,
    base_url: Optional[str] = None,
    video: str = "off",
    trace: str = "retain-on-failure",
    screenshot: str = "only-on-failure",
    timeout: Optional[int] = None,
    output_dir: str = ".",
    plugins: list = None,
) -> tuple[list, dict]:
    plugins = plugins or []
    run_id = f"run_{get_timestamp()}"
    evidence_base = os.path.join(output_dir, EVIDENCE_DIR, run_id)
    report_base = os.path.join(output_dir, REPORTS_DIR, run_id)
    
    args = [sys.executable, "-m", "pytest"]
    env = os.environ.copy()
    
    if path:
        args.append(path)
    
    if suite:
        args.extend(["-m", suite])
    
    if filter_expr:
        args.extend(["-k", filter_expr])
    
    if rerun_failed and os.path.exists(LAST_FAILED_FILE):
        with open(LAST_FAILED_FILE) as f:
            last_failed = json.load(f)
            if last_failed.get("failed_tests"):
                args.extend(last_failed["failed_tests"])
    
    if max_failures:
        args.extend(["--maxfail", str(max_failures)])
    
    if parallel > 1 and "pytest-xdist" in plugins:
        args.extend(["-n", str(parallel)])
    
    if timeout:
        args.extend(["--timeout", str(timeout)])
    
    args.extend(["-v", "--tb=short"])
    
    if "pytest-json-report" in plugins:
        json_report = f"{report_base}.json"
        args.extend(["--json-report", f"--json-report-file={json_report}"])
    
    if "pytest-html" in plugins:
        html_report = f"{report_base}.html"
        args.extend([f"--html={html_report}", "--self-contained-html"])
    
    if "pytest-playwright" in plugins:
        playwright_args = [
            f"--video={video}",
            f"--tracing={trace}",
            f"--screenshot={screenshot}",
            "--browser=chromium",
            f"--output={evidence_base}",
        ]
        if os.environ.get("HEADED"):
            playwright_args.append("--headed")
        args.extend(playwright_args)
    
    if base_url:
        env["BASE_URL"] = base_url
    
    env["EVIDENCE_TEMP_DIR"] = evidence_base
    env["PYTHONUNBUFFERED"] = "1"
    
    Path(evidence_base).mkdir(parents=True, exist_ok=True)
    Path(report_base).parent.mkdir(parents=True, exist_ok=True)
    
    return args, env, run_id, evidence_base, report_base


def parse_pytest_output(returncode: int, stdout: str, stderr: str) -> dict:
    result = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "total": 0,
        "failures": [],
    }
    
    import re
    
    summary_pattern = r"(\d+) passed|(\d+) failed|(\d+) skipped|(\d+) error"
    for match in re.finditer(summary_pattern, stdout + stderr):
        if match.group(1):
            result["passed"] = int(match.group(1))
        if match.group(2):
            result["failed"] = int(match.group(2))
        if match.group(3):
            result["skipped"] = int(match.group(3))
        if match.group(4):
            result["errors"] = int(match.group(4))
    
    result["total"] = result["passed"] + result["failed"] + result["skipped"] + result["errors"]
    
    failure_pattern = r"FAILED\s+(\S+)"
    for match in re.finditer(failure_pattern, stdout):
        test_id = match.group(1)
        result["failures"].append({
            "name": test_id.split("::")[-1] if "::" in test_id else test_id,
            "file": test_id,
            "error_type": "TestFailure",
            "error_message": "",
        })
    
    return result


def parse_json_report(report_path: str) -> dict:
    if not os.path.exists(report_path):
        return {}
    
    with open(report_path) as f:
        report = json.load(f)
    
    result = {
        "passed": report.get("summary", {}).get("passed", 0),
        "failed": report.get("summary", {}).get("failed", 0),
        "skipped": report.get("summary", {}).get("skipped", 0),
        "errors": report.get("summary", {}).get("error", 0),
        "total": report.get("summary", {}).get("total", 0),
        "duration_sec": report.get("duration", 0),
        "failures": [],
    }
    
    for test in report.get("tests", []):
        if test.get("outcome") == "failed":
            call_info = test.get("call", {})
            result["failures"].append({
                "name": test.get("nodeid", "").split("::")[-1],
                "file": test.get("nodeid", ""),
                "error_type": call_info.get("crash", {}).get("message", "TestFailure"),
                "error_message": call_info.get("longrepr", ""),
            })
    
    return result


def save_last_failed(failures: list):
    failed_tests = [f["file"] for f in failures if f.get("file")]
    with open(LAST_FAILED_FILE, "w") as f:
        json.dump({
            "timestamp": get_timestamp(),
            "failed_tests": failed_tests,
        }, f, indent=2)


def run_collect_evidence(test_name: str, evidence_dir: str, services: list):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    collect_script = os.path.join(script_dir, "collect_evidence.py")
    
    if os.path.exists(collect_script):
        cmd = [
            sys.executable, collect_script, "finalize",
            "--test-name", test_name,
            "--temp-dir", evidence_dir,
            "--output", evidence_dir,
        ]
        if services:
            cmd.extend(["--services", ",".join(services)])
        
        subprocess.run(cmd, capture_output=True)


def generate_run_index(evidence_base: str, run_id: str, failures: list):
    index = {
        "run_id": run_id,
        "generated_at": get_timestamp(),
        "tests": {},
    }
    
    for failure in failures:
        test_name = failure.get("name", "")
        test_dir = os.path.join(evidence_base, test_name)
        if os.path.isdir(test_dir):
            files = {}
            for f in Path(test_dir).rglob("*"):
                if f.is_file():
                    rel_path = str(f.relative_to(test_dir))
                    if f.suffix == ".zip" and "trace" in f.name:
                        files["trace"] = rel_path
                    elif f.suffix == ".png":
                        if "screenshots" not in files:
                            files["screenshots"] = []
                        files["screenshots"].append(rel_path)
                    elif f.suffix in [".webm", ".mp4"]:
                        files["video"] = rel_path
                    elif f.name == "console.json":
                        files["console"] = rel_path
                    elif f.name == "network.json":
                        files["network"] = rel_path
                    elif "dom" in f.name and f.suffix == ".html":
                        files["dom"] = rel_path
                    elif f.suffix == ".log":
                        if "service_logs" not in files:
                            files["service_logs"] = []
                        files["service_logs"].append(rel_path)
            
            index["tests"][test_name] = {
                "status": "failed",
                "error_message": failure.get("error_message", ""),
                "files": files,
            }
    
    index_path = os.path.join(evidence_base, "evidence_index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Run tests with structured JSON output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", help="Test file or directory")
    parser.add_argument("--suite", help="Test suite marker (e.g., smoke, regression)")
    parser.add_argument("--filter", dest="filter_expr", help="pytest -k filter expression")
    parser.add_argument("--rerun-failed", action="store_true", help="Rerun last failed tests")
    parser.add_argument("--max-failures", type=int, help="Stop after N failures")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers")
    parser.add_argument("--base-url", help="Base URL (default: from runtime.json)")
    parser.add_argument("--service", default="frontend", help="Service name for base URL")
    parser.add_argument("--video", choices=["on", "off", "retain-on-failure"], default="off")
    parser.add_argument("--trace", choices=["on", "off", "retain-on-failure"], default="retain-on-failure")
    parser.add_argument("--screenshot", choices=["on", "off", "only-on-failure"], default="only-on-failure")
    parser.add_argument("--timeout", type=int, help="Test timeout in seconds")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--collect-on-fail", action="store_true", default=True, help="Collect evidence on failure")
    parser.add_argument("--no-collect", action="store_true", help="Disable evidence collection")
    
    args = parser.parse_args()
    
    ensure_dirs()
    plugins = detect_plugins()
    
    base_url = args.base_url or get_base_url(args.service)
    
    pytest_args, env, run_id, evidence_base, report_base = build_pytest_args(
        path=args.path,
        suite=args.suite,
        filter_expr=args.filter_expr,
        rerun_failed=args.rerun_failed,
        max_failures=args.max_failures,
        parallel=args.parallel,
        base_url=base_url,
        video=args.video,
        trace=args.trace,
        screenshot=args.screenshot,
        timeout=args.timeout,
        output_dir=args.output_dir,
        plugins=plugins,
    )
    
    start_time = datetime.now()
    
    process = subprocess.run(
        pytest_args,
        env=env,
        capture_output=True,
        text=True,
    )
    
    duration = (datetime.now() - start_time).total_seconds()
    
    json_report_path = f"{report_base}.json"
    html_report_path = f"{report_base}.html"
    
    if "pytest-json-report" in plugins and os.path.exists(json_report_path):
        result = parse_json_report(json_report_path)
    else:
        result = parse_pytest_output(process.returncode, process.stdout, process.stderr)
    
    result["duration_sec"] = round(duration, 2)
    
    runtime = load_runtime()
    services = list(runtime.get("services", {}).keys())
    
    for failure in result.get("failures", []):
        test_name = failure["name"]
        test_evidence_dir = os.path.join(evidence_base, test_name)
        failure["evidence_dir"] = test_evidence_dir
        
        if args.collect_on_fail and not args.no_collect:
            run_collect_evidence(test_name, evidence_base, services)
    
    if result.get("failures"):
        save_last_failed(result["failures"])
        if args.collect_on_fail and not args.no_collect:
            generate_run_index(evidence_base, run_id, result["failures"])
    
    status = "passed" if process.returncode == 0 else "failed"
    
    output = {
        "status": status,
        "run_id": run_id,
        "summary": {
            "total": result.get("total", 0),
            "passed": result.get("passed", 0),
            "failed": result.get("failed", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", 0),
            "duration_sec": result.get("duration_sec", 0),
        },
        "failures": result.get("failures", []),
        "evidence_base": evidence_base,
        "base_url": base_url,
    }
    
    if os.path.exists(html_report_path):
        output["report_html"] = html_report_path
    if os.path.exists(json_report_path):
        output["report_json"] = json_report_path
    
    print(json.dumps(output, indent=2))
    
    sys.exit(0 if status == "passed" else 1)


if __name__ == "__main__":
    main()
