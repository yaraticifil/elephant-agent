#!/usr/bin/env python3
"""
Issue report generator for test failures.

Creates structured markdown reports from test failures with evidence,
environment info, and placeholders for fix/regression tracking.

Usage:
    python report_issue.py --test-name test_login --evidence-dir .verdent/testing/evidence/run_xxx/test_login/
    python report_issue.py --append-fix report.md --fix-description "Fixed token parsing"
    python report_issue.py --append-regression report.md --regression-result "PASSED"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


RUNTIME_FILE = ".verdent/testing/runtime.json"
ISSUES_DIR = ".verdent/testing/issues"


def get_timestamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def get_timestamp_for_filename():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs():
    Path(ISSUES_DIR).mkdir(parents=True, exist_ok=True)


def load_runtime() -> dict:
    if os.path.exists(RUNTIME_FILE):
        with open(RUNTIME_FILE) as f:
            return json.load(f)
    return {"services": {}}


def get_git_info() -> dict:
    info = {"commit": "unknown", "branch": "unknown"}
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()
        
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
    except Exception:
        pass
    return info


def load_evidence_index(evidence_dir: str) -> dict:
    index_file = os.path.join(evidence_dir, "evidence_index.json")
    if os.path.exists(index_file):
        with open(index_file) as f:
            return json.load(f)
    return {}


def extract_repro_steps_from_trace(trace_path: str) -> list:
    steps = []
    if not os.path.exists(trace_path):
        return steps
    
    try:
        with zipfile.ZipFile(trace_path, 'r') as zf:
            action_files = [
                n for n in zf.namelist() 
                if n.endswith('.json') and any(x in n.lower() for x in ['action', 'trace', 'event'])
            ]
            
            for name in action_files:
                try:
                    with zf.open(name) as f:
                        content = f.read().decode('utf-8')
                        data = json.loads(content)
                        
                        actions = []
                        if isinstance(data, list):
                            actions = data
                        elif isinstance(data, dict):
                            actions = data.get("actions", [])
                            if not actions:
                                actions = data.get("events", [])
                            if not actions and "traceEvents" in data:
                                actions = data.get("traceEvents", [])
                        
                        for action in actions[:20]:
                            if not isinstance(action, dict):
                                continue
                            
                            action_type = action.get("type", "") or action.get("name", "") or action.get("method", "")
                            action_type = action_type.lower()
                            
                            params = action.get("params", {}) or action
                            selector = params.get("selector", "") or action.get("selector", "")
                            url = params.get("url", "") or action.get("url", "")
                            
                            if "goto" in action_type or "navigate" in action_type:
                                if url:
                                    steps.append(f"Navigate to `{url}`")
                            elif "click" in action_type:
                                if selector:
                                    steps.append(f"Click on `{selector}`")
                            elif "fill" in action_type or "type" in action_type:
                                if selector:
                                    steps.append(f"Fill `{selector}` with value")
                            elif "press" in action_type:
                                if selector:
                                    steps.append(f"Press key on `{selector}`")
                            elif "wait" in action_type:
                                if selector:
                                    steps.append(f"Wait for `{selector}`")
                        
                        if steps:
                            break
                except Exception:
                    continue
    except Exception:
        pass
    
    return steps


def format_console_errors(errors: list) -> str:
    if not errors:
        return "_No console errors captured_"
    
    lines = []
    for err in errors[:10]:
        level = err.get("level", "error")
        text = err.get("text", "")[:200]
        lines.append(f"- [{level}] {text}")
    return "\n".join(lines)


def format_failed_requests(requests: list) -> str:
    if not requests:
        return "_No failed requests captured_"
    
    lines = []
    for req in requests[:10]:
        method = req.get("method", "GET")
        url = req.get("url", "")[:100]
        status = req.get("status", "?")
        lines.append(f"- {method} {url} → {status}")
    return "\n".join(lines)


def format_service_errors(errors: dict) -> str:
    if not errors:
        return "_No service errors captured_"
    
    sections = []
    for service, error_lines in errors.items():
        lines = [f"**{service}:**"]
        for line in error_lines[:5]:
            lines.append(f"```\n{line[:300]}\n```")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def format_services_table(services: dict) -> str:
    if not services:
        return "_No services running_"
    
    lines = ["| Service | URL | Command |", "|---------|-----|---------|"]
    for name, info in services.items():
        url = info.get("url", "N/A")
        cmd = info.get("command", "N/A")[:50]
        lines.append(f"| {name} | {url} | `{cmd}` |")
    return "\n".join(lines)


def format_evidence_links(evidence_dir: str, files: dict, output_dir: str = "") -> str:
    if not files:
        return "_No evidence files_"
    
    lines = []
    
    if output_dir and evidence_dir.startswith(os.path.dirname(output_dir)):
        try:
            rel_evidence = os.path.relpath(evidence_dir, os.path.dirname(output_dir))
        except ValueError:
            rel_evidence = evidence_dir
    else:
        rel_evidence = evidence_dir
    
    if "trace" in files:
        lines.append(f"- [Trace]({rel_evidence}/{files['trace']}) - View at [trace.playwright.dev](https://trace.playwright.dev)")
    
    if "failure_screenshot" in files:
        lines.append(f"- [Failure Screenshot]({rel_evidence}/{files['failure_screenshot']})")
    
    if "screenshots" in files:
        for ss in files["screenshots"][:5]:
            lines.append(f"- [Screenshot]({rel_evidence}/{ss})")
    
    if "video" in files:
        lines.append(f"- [Video]({rel_evidence}/{files['video']})")
    
    if "console" in files:
        lines.append(f"- [Console Logs]({rel_evidence}/{files['console']})")
    
    if "network" in files:
        lines.append(f"- [Network Logs]({rel_evidence}/{files['network']})")
    
    if "dom" in files:
        lines.append(f"- [DOM Snapshot]({rel_evidence}/{files['dom']})")
    
    if "service_logs" in files:
        for log in files["service_logs"]:
            lines.append(f"- [Service Log: {log}]({rel_evidence}/{log})")
    
    return "\n".join(lines) if lines else "_No evidence files_"


def generate_report(
    test_name: str,
    evidence_dir: str,
    error_message: str = "",
    expected: str = "",
    actual: str = "",
    output_dir: str = ISSUES_DIR,
) -> str:
    ensure_dirs()
    
    git_info = get_git_info()
    runtime = load_runtime()
    evidence = load_evidence_index(evidence_dir)
    
    trace_path = os.path.join(evidence_dir, evidence.get("files", {}).get("trace", "trace.zip"))
    repro_steps = extract_repro_steps_from_trace(trace_path)
    
    if repro_steps:
        repro_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(repro_steps)])
    else:
        repro_text = "_Unable to extract reproduction steps. Check trace file manually._"
    
    if not expected:
        expected = "_Expected behavior not specified_"
    if not actual:
        actual = error_message if error_message else "_Actual behavior not specified_"
    
    console_errors = format_console_errors(evidence.get("console_errors", []))
    failed_requests = format_failed_requests(evidence.get("failed_requests", []))
    service_errors = format_service_errors(evidence.get("service_errors", {}))
    services_table = format_services_table(runtime.get("services", {}))
    evidence_links = format_evidence_links(evidence_dir, evidence.get("files", {}), output_dir)
    
    error_block = error_message if error_message else "_No error message provided_"
    
    report = f"""# [FAILED] {test_name}

## Environment

| Item | Value |
|------|-------|
| Timestamp | {get_timestamp()} |
| Git Commit | `{git_info['commit']}` |
| Git Branch | `{git_info['branch']}` |

### Services

{services_table}

## Reproduction Steps

{repro_text}

## Expected vs Actual

| Expected | Actual |
|----------|--------|
| {expected} | {actual} |

## Error Message

```
{error_block}
```

## Key Log Summary

### Console Errors

{console_errors}

### Failed Requests

{failed_requests}

### Service Errors

{service_errors}

## Evidence Files

{evidence_links}

## Fix Description

<!-- Agent: Describe the fix applied -->

_Pending fix_

## Regression Result

<!-- Agent: Record regression test result after fix -->

_Pending regression test_
"""
    
    filename = f"{get_timestamp_for_filename()}_{test_name}.md"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w") as f:
        f.write(report)
    
    return filepath


def append_fix(report_path: str, fix_description: str) -> bool:
    if not os.path.exists(report_path):
        return False
    
    with open(report_path) as f:
        content = f.read()
    
    pattern = r"(## Fix Description\n\n<!-- .+ -->\n\n)(_Pending fix_|.+?)(\n\n## Regression Result)"
    replacement = f"\\g<1>{fix_description}\n\n_Fixed at {get_timestamp()}_\\3"
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open(report_path, "w") as f:
        f.write(new_content)
    
    return True


def append_regression(report_path: str, regression_result: str) -> bool:
    if not os.path.exists(report_path):
        return False
    
    with open(report_path) as f:
        content = f.read()
    
    pattern = r"(## Regression Result\n\n<!-- .+ -->\n\n)(_Pending regression test_|.+?)$"
    replacement = f"\\g<1>**{regression_result}** at {get_timestamp()}"
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open(report_path, "w") as f:
        f.write(new_content)
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate and update issue reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("--test-name", help="Failed test name")
    parser.add_argument("--evidence-dir", help="Evidence directory")
    parser.add_argument("--error-message", default="", help="Error message")
    parser.add_argument("--expected", default="", help="Expected behavior")
    parser.add_argument("--actual", default="", help="Actual behavior")
    parser.add_argument("--output-dir", default=ISSUES_DIR, help="Output directory")
    
    parser.add_argument("--append-fix", help="Report file to append fix to")
    parser.add_argument("--fix-description", help="Fix description")
    
    parser.add_argument("--append-regression", help="Report file to append regression to")
    parser.add_argument("--regression-result", help="Regression result (PASSED/FAILED)")
    
    args = parser.parse_args()
    
    if args.append_fix:
        if not args.fix_description:
            print(json.dumps({"status": "error", "message": "--fix-description required"}))
            sys.exit(1)
        success = append_fix(args.append_fix, args.fix_description)
        print(json.dumps({"status": "ok" if success else "error", "path": args.append_fix}))
        sys.exit(0 if success else 1)
    
    if args.append_regression:
        if not args.regression_result:
            print(json.dumps({"status": "error", "message": "--regression-result required"}))
            sys.exit(1)
        success = append_regression(args.append_regression, args.regression_result)
        print(json.dumps({"status": "ok" if success else "error", "path": args.append_regression}))
        sys.exit(0 if success else 1)
    
    if not args.test_name:
        print(json.dumps({"status": "error", "message": "--test-name required"}))
        sys.exit(1)
    
    evidence_dir = args.evidence_dir or ""
    
    filepath = generate_report(
        test_name=args.test_name,
        evidence_dir=evidence_dir,
        error_message=args.error_message,
        expected=args.expected,
        actual=args.actual,
        output_dir=args.output_dir,
    )
    
    print(json.dumps({
        "status": "ok",
        "path": filepath,
        "test_name": args.test_name,
    }, indent=2))


if __name__ == "__main__":
    main()
