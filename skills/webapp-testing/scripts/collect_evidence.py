#!/usr/bin/env python3
"""
Evidence collection and organization tool.

Collects and organizes test failure evidence including traces, screenshots,
logs, and service output into a structured directory.

Usage:
    python collect_evidence.py finalize --test-name test_login --temp-dir /tmp/evidence --output .verdent/testing/evidence/
    python collect_evidence.py cleanup --days 7
    python collect_evidence.py index --evidence-dir .verdent/testing/evidence/run_xxx/
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


RUNTIME_FILE = ".verdent/testing/runtime.json"
LOGS_DIR = ".verdent/testing/logs"


def get_timestamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def load_runtime() -> dict:
    if os.path.exists(RUNTIME_FILE):
        with open(RUNTIME_FILE) as f:
            return json.load(f)
    return {"services": {}}


def copy_if_exists(src: str, dst: str):
    if os.path.exists(src):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return True
    return False


def find_files(directory: str, patterns: list) -> list:
    found = []
    if not os.path.exists(directory):
        return found
    
    for root, _, files in os.walk(directory):
        for f in files:
            for pattern in patterns:
                if re.search(pattern, f, re.IGNORECASE):
                    found.append(os.path.join(root, f))
                    break
    return found


def extract_console_errors(console_file: str) -> list:
    if not os.path.exists(console_file):
        return []
    
    errors = []
    try:
        with open(console_file) as f:
            logs = json.load(f)
            for entry in logs:
                if entry.get("level") in ["error", "warning"]:
                    errors.append({
                        "level": entry.get("level"),
                        "text": entry.get("text", "")[:500],
                    })
    except Exception:
        pass
    
    return errors[:20]


def extract_failed_requests(network_file: str) -> list:
    if not os.path.exists(network_file):
        return []
    
    failed = []
    try:
        with open(network_file) as f:
            logs = json.load(f)
            for entry in logs:
                status = entry.get("status", 0)
                if status >= 400 or entry.get("failed"):
                    failed.append({
                        "method": entry.get("method", "GET"),
                        "url": entry.get("url", "")[:200],
                        "status": status,
                    })
    except Exception:
        pass
    
    return failed[:20]


def extract_service_errors(log_file: str, max_lines: int = 50) -> list:
    if not os.path.exists(log_file):
        return []
    
    errors = []
    error_patterns = [
        r"error",
        r"exception",
        r"traceback",
        r"failed",
        r"fatal",
    ]
    
    try:
        with open(log_file) as f:
            lines = f.readlines()
            in_traceback = False
            traceback_lines = []
            
            for line in lines[-500:]:
                line_lower = line.lower()
                
                if "traceback" in line_lower:
                    in_traceback = True
                    traceback_lines = [line.rstrip()]
                    continue
                
                if in_traceback:
                    traceback_lines.append(line.rstrip())
                    if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                        errors.append("\n".join(traceback_lines))
                        in_traceback = False
                        traceback_lines = []
                    continue
                
                for pattern in error_patterns:
                    if re.search(pattern, line_lower):
                        errors.append(line.rstrip())
                        break
    except Exception:
        pass
    
    return errors[-max_lines:]


def finalize_evidence(
    test_name: str,
    temp_dir: str,
    output_dir: str,
    services: list = None,
    time_range: tuple = None,
) -> dict:
    test_evidence_dir = os.path.join(output_dir, test_name)
    Path(test_evidence_dir).mkdir(parents=True, exist_ok=True)
    
    collected = {
        "test_name": test_name,
        "collected_at": get_timestamp(),
        "files": {},
    }
    
    trace_files = find_files(temp_dir, [r"trace.*\.zip$", f"{test_name}.*trace"])
    for trace in trace_files:
        dst = os.path.join(test_evidence_dir, "trace.zip")
        if copy_if_exists(trace, dst):
            collected["files"]["trace"] = "trace.zip"
            break
    
    screenshot_patterns = [
        f"{test_name}.*\\.png$",
        r"failure.*\.png$",
        r"screenshot.*\.png$",
    ]
    screenshots = find_files(temp_dir, screenshot_patterns)
    if screenshots:
        screenshots_dir = os.path.join(test_evidence_dir, "screenshots")
        Path(screenshots_dir).mkdir(exist_ok=True)
        collected["files"]["screenshots"] = []
        for i, ss in enumerate(screenshots[:10]):
            name = os.path.basename(ss)
            if "failure" in name.lower():
                dst_name = "failure_screenshot.png"
            else:
                dst_name = f"step_{i+1:03d}.png"
            dst = os.path.join(screenshots_dir, dst_name)
            if copy_if_exists(ss, dst):
                collected["files"]["screenshots"].append(f"screenshots/{dst_name}")
        
        failure_ss = os.path.join(temp_dir, f"{test_name}_failure.png")
        if os.path.exists(failure_ss):
            dst = os.path.join(test_evidence_dir, "failure_screenshot.png")
            copy_if_exists(failure_ss, dst)
            collected["files"]["failure_screenshot"] = "failure_screenshot.png"
    
    video_files = find_files(temp_dir, [r"\.webm$", r"\.mp4$"])
    for video in video_files:
        ext = os.path.splitext(video)[1]
        dst = os.path.join(test_evidence_dir, f"video{ext}")
        if copy_if_exists(video, dst):
            collected["files"]["video"] = f"video{ext}"
            break
    
    console_file = os.path.join(temp_dir, f"{test_name}_console.json")
    if os.path.exists(console_file):
        dst = os.path.join(test_evidence_dir, "console.json")
        copy_if_exists(console_file, dst)
        collected["files"]["console"] = "console.json"
        collected["console_errors"] = extract_console_errors(dst)
    
    network_file = os.path.join(temp_dir, f"{test_name}_network.json")
    if os.path.exists(network_file):
        dst = os.path.join(test_evidence_dir, "network.json")
        copy_if_exists(network_file, dst)
        collected["files"]["network"] = "network.json"
        collected["failed_requests"] = extract_failed_requests(dst)
    
    dom_file = os.path.join(temp_dir, f"{test_name}_dom.html")
    if os.path.exists(dom_file):
        dst = os.path.join(test_evidence_dir, "dom_snapshot.html")
        copy_if_exists(dom_file, dst)
        collected["files"]["dom"] = "dom_snapshot.html"
    
    if services:
        collected["files"]["service_logs"] = []
        collected["service_errors"] = {}
        
        for service in services:
            log_file = os.path.join(LOGS_DIR, f"{service}.log")
            if os.path.exists(log_file):
                dst = os.path.join(test_evidence_dir, f"{service}.log")
                copy_if_exists(log_file, dst)
                collected["files"]["service_logs"].append(f"{service}.log")
                
                errors = extract_service_errors(dst)
                if errors:
                    collected["service_errors"][service] = errors
    
    index_file = os.path.join(test_evidence_dir, "evidence_index.json")
    with open(index_file, "w") as f:
        json.dump(collected, f, indent=2)
    
    return collected


def cleanup_old_evidence(evidence_base: str, days: int = 7) -> dict:
    cutoff = datetime.now() - timedelta(days=days)
    removed = []
    
    evidence_path = Path(evidence_base)
    if not evidence_path.exists():
        return {"status": "ok", "removed": removed}
    
    for run_dir in evidence_path.iterdir():
        if not run_dir.is_dir():
            continue
        
        if run_dir.name.startswith("run_"):
            try:
                timestamp_str = run_dir.name.replace("run_", "")
                run_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                if run_time < cutoff:
                    shutil.rmtree(run_dir)
                    removed.append(run_dir.name)
            except ValueError:
                pass
    
    return {"status": "ok", "removed": removed, "count": len(removed)}


def regenerate_index(evidence_dir: str) -> dict:
    index = {
        "generated_at": get_timestamp(),
        "tests": {},
    }
    
    evidence_path = Path(evidence_dir)
    if not evidence_path.exists():
        return {"status": "error", "message": "Directory not found"}
    
    for test_dir in evidence_path.iterdir():
        if not test_dir.is_dir():
            continue
        if test_dir.name == "evidence_index.json":
            continue
        
        test_name = test_dir.name
        files = {}
        
        for f in test_dir.rglob("*"):
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
                elif f.name == "dom_snapshot.html":
                    files["dom"] = rel_path
                elif f.suffix == ".log":
                    if "service_logs" not in files:
                        files["service_logs"] = []
                    files["service_logs"].append(rel_path)
        
        index["tests"][test_name] = {
            "files": files,
        }
    
    index_file = evidence_path / "evidence_index.json"
    with open(index_file, "w") as f:
        json.dump(index, f, indent=2)
    
    return {"status": "ok", "tests": list(index["tests"].keys())}


def main():
    parser = argparse.ArgumentParser(
        description="Evidence collection and organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    finalize_parser = subparsers.add_parser("finalize", help="Finalize evidence collection")
    finalize_parser.add_argument("--test-name", required=True, help="Test name")
    finalize_parser.add_argument("--temp-dir", required=True, help="Temp evidence directory")
    finalize_parser.add_argument("--output", required=True, help="Output directory")
    finalize_parser.add_argument("--services", help="Comma-separated service names")
    finalize_parser.add_argument("--time-range", help="Time range (start/end ISO format)")

    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old evidence")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Remove evidence older than N days")
    cleanup_parser.add_argument("--evidence-dir", default=".verdent/testing/evidence", help="Evidence base directory")

    index_parser = subparsers.add_parser("index", help="Regenerate evidence index")
    index_parser.add_argument("--evidence-dir", required=True, help="Evidence directory")

    args = parser.parse_args()

    if args.command == "finalize":
        services = args.services.split(",") if args.services else []
        time_range = None
        if args.time_range:
            parts = args.time_range.split("/")
            if len(parts) == 2:
                time_range = (parts[0], parts[1])
        
        result = finalize_evidence(
            test_name=args.test_name,
            temp_dir=args.temp_dir,
            output_dir=args.output,
            services=services,
            time_range=time_range,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "cleanup":
        result = cleanup_old_evidence(args.evidence_dir, args.days)
        print(json.dumps(result, indent=2))

    elif args.command == "index":
        result = regenerate_index(args.evidence_dir)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
