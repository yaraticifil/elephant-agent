#!/usr/bin/env python3
"""
Service lifecycle manager for web application testing.

Manages starting, stopping, restarting services with health checks,
dynamic port discovery, and structured logging.

Usage:
    python server_manager.py start --service "npm run dev" --name frontend --port auto
    python server_manager.py stop --name frontend
    python server_manager.py restart --name backend
    python server_manager.py status --json
    python server_manager.py logs --name backend --tail 50
"""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


RUNTIME_FILE = ".verdent/testing/runtime.json"
LOGS_DIR = ".verdent/testing/logs"


def get_timestamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs():
    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
    Path(RUNTIME_FILE).parent.mkdir(parents=True, exist_ok=True)


def load_runtime() -> dict:
    if os.path.exists(RUNTIME_FILE):
        with open(RUNTIME_FILE) as f:
            return json.load(f)
    return {"services": {}, "updated_at": None}


def save_runtime(data: dict):
    data["updated_at"] = get_timestamp()
    with open(RUNTIME_FILE, "w") as f:
        json.dump(data, f, indent=2)


def output_json(data: dict):
    print(json.dumps(data, indent=2))


def output_error(message: str, code: int = 1):
    output_json({"status": "error", "message": message})
    sys.exit(code)


def is_port_open(port: int, host: str = "localhost", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.error, ConnectionRefusedError, OSError):
        return False


def http_health_check(url: str, timeout: float = 5.0) -> bool:
    if not HAS_HTTPX:
        return False
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False


def command_health_check(cmd: str) -> bool:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def wait_for_health(
    port: int,
    health_check: str = "tcp",
    timeout: int = 60,
    interval: float = 1.0
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if health_check == "tcp":
            if is_port_open(port):
                return True
        elif health_check.startswith("http"):
            url = health_check.replace("PORT", str(port))
            if http_health_check(url):
                return True
        else:
            cmd = health_check.replace("PORT", str(port))
            if command_health_check(cmd):
                return True
        time.sleep(interval)
    return False


def parse_port_from_output(line: str) -> Optional[int]:
    patterns = [
        r'"port"\s*:\s*(\d+)',
        r"port[:\s]+(\d+)",
        r"localhost:(\d+)",
        r"127\.0\.0\.1:(\d+)",
        r":(\d+)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            port = int(match.group(1))
            if 1024 <= port <= 65535:
                return port
    return None


def read_port_from_file(path: str, timeout: int = 30) -> Optional[int]:
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(path):
            with open(path) as f:
                content = f.read().strip()
                if content.isdigit():
                    return int(content)
                port = parse_port_from_output(content)
                if port:
                    return port
        time.sleep(0.5)
    return None


def kill_process_tree(pid: int, sig=signal.SIGTERM):
    if HAS_PSUTIL:
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.send_signal(sig)
                except psutil.NoSuchProcess:
                    pass
            parent.send_signal(sig)
        except psutil.NoSuchProcess:
            pass
    else:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def is_process_running(pid: int) -> bool:
    if HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False


class ServiceManager:
    def __init__(self):
        ensure_dirs()
        self.runtime = load_runtime()

    def start_service(
        self,
        name: str,
        command: str,
        port: str,
        health_check: str = "tcp",
        timeout: int = 60,
        port_file: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> dict:
        if name in self.runtime["services"]:
            svc = self.runtime["services"][name]
            if is_process_running(svc.get("pid", 0)):
                return {"status": "already_running", "service": svc}

        log_file = os.path.join(LOGS_DIR, f"{name}.log")
        
        with open(log_file, "w") as log_f:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None,
            )

        actual_port = None
        port_mode = "fixed"
        if port_file:
            port_mode = "file"
            actual_port = read_port_from_file(port_file, timeout)
        elif port == "auto":
            port_mode = "auto"
            time.sleep(2)
            with open(log_file) as f:
                for line in f:
                    actual_port = parse_port_from_output(line)
                    if actual_port:
                        break
            if not actual_port:
                for _ in range(timeout - 2):
                    time.sleep(1)
                    with open(log_file) as f:
                        for line in f:
                            actual_port = parse_port_from_output(line)
                            if actual_port:
                                break
                    if actual_port:
                        break
        else:
            actual_port = int(port)

        if not actual_port:
            kill_process_tree(process.pid, signal.SIGKILL)
            return {"status": "error", "message": "Failed to detect port"}

        if not wait_for_health(actual_port, health_check, timeout):
            kill_process_tree(process.pid, signal.SIGKILL)
            return {"status": "error", "message": f"Health check failed on port {actual_port}"}

        service_info = {
            "pid": process.pid,
            "port": actual_port,
            "port_mode": port_mode,
            "port_file": port_file,
            "url": f"http://localhost:{actual_port}",
            "command": command,
            "started_at": get_timestamp(),
            "log_file": log_file,
            "health_check": health_check,
            "cwd": cwd,
        }
        
        self.runtime["services"][name] = service_info
        save_runtime(self.runtime)
        
        return {"status": "started", "service": service_info}

    def stop_service(self, name: str, timeout: int = 10) -> dict:
        if name not in self.runtime["services"]:
            return {"status": "not_found", "message": f"Service '{name}' not found"}
        
        svc = self.runtime["services"][name]
        pid = svc.get("pid")
        port = svc.get("port")
        
        if not is_process_running(pid):
            del self.runtime["services"][name]
            save_runtime(self.runtime)
            return {"status": "not_running", "message": "Process was not running"}

        kill_process_tree(pid, signal.SIGTERM)
        
        start = time.time()
        while time.time() - start < timeout:
            if not is_process_running(pid):
                break
            time.sleep(0.5)
        
        if is_process_running(pid):
            kill_process_tree(pid, signal.SIGKILL)
            time.sleep(1)

        if isinstance(port, int) and port > 0:
            start = time.time()
            while time.time() - start < 5:
                if not is_port_open(port):
                    break
                time.sleep(0.5)

        del self.runtime["services"][name]
        save_runtime(self.runtime)
        
        return {"status": "stopped", "name": name}

    def restart_service(self, name: str, timeout: int = 60) -> dict:
        if name not in self.runtime["services"]:
            return {"status": "error", "message": f"Service '{name}' not found"}
        
        svc = self.runtime["services"][name]
        command = svc.get("command")
        port_mode = svc.get("port_mode", "fixed")
        port_file = svc.get("port_file")
        health_check = svc.get("health_check", "tcp")
        cwd = svc.get("cwd")
        
        if port_mode == "auto":
            port = "auto"
        elif port_mode == "file" and port_file:
            port = "auto"
        else:
            port = str(svc.get("port"))
        
        stop_result = self.stop_service(name)
        if stop_result["status"] == "error":
            return stop_result
        
        time.sleep(1)
        
        return self.start_service(name, command, port, health_check, timeout, port_file, cwd)

    def reload_service(self, name: str, endpoint: str) -> dict:
        if name not in self.runtime["services"]:
            return {"status": "error", "message": f"Service '{name}' not found"}
        
        if not HAS_HTTPX:
            return {"status": "error", "message": "httpx not installed, cannot call reload endpoint"}
        
        svc = self.runtime["services"][name]
        port = svc.get("port")
        
        parts = endpoint.split(" ", 1)
        method = "POST"
        url = endpoint
        if len(parts) == 2 and parts[0].upper() in ["GET", "POST", "PUT", "PATCH"]:
            method = parts[0].upper()
            url = parts[1]
        
        url = url.replace("PORT", str(port))
        
        try:
            response = httpx.request(method, url, timeout=30)
            return {
                "status": "reloaded" if response.status_code < 400 else "error",
                "http_status": response.status_code,
                "response": response.text[:500],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def wait_ready(self, name: str, timeout: int = 60) -> dict:
        if name not in self.runtime["services"]:
            return {"status": "error", "message": f"Service '{name}' not found"}
        
        svc = self.runtime["services"][name]
        port = svc.get("port")
        health_check = svc.get("health_check", "tcp")
        
        if wait_for_health(port, health_check, timeout):
            return {"status": "ready", "name": name, "port": port}
        else:
            return {"status": "error", "message": f"Health check timed out for {name}"}

    def get_status(self) -> dict:
        status = {"services": {}}
        for name, svc in list(self.runtime["services"].items()):
            pid = svc.get("pid")
            port = svc.get("port")
            running = is_process_running(pid) if pid else False
            healthy = is_port_open(port) if isinstance(port, int) and port > 0 else False
            status["services"][name] = {
                **svc,
                "running": running,
                "healthy": healthy,
            }
            if not running:
                del self.runtime["services"][name]
        save_runtime(self.runtime)
        return status

    def get_logs(self, name: str, tail: Optional[int] = None, since: Optional[str] = None) -> dict:
        if name not in self.runtime["services"]:
            return {"status": "error", "message": f"Service '{name}' not found"}
        
        log_file = self.runtime["services"][name].get("log_file")
        if not log_file or not os.path.exists(log_file):
            return {"status": "error", "message": "Log file not found"}
        
        with open(log_file) as f:
            lines = f.readlines()
        
        if tail:
            lines = lines[-tail:]
        
        return {"status": "ok", "lines": [l.rstrip() for l in lines]}

    def stop_all(self, timeout: int = 10) -> dict:
        results = {}
        for name in list(self.runtime["services"].keys()):
            results[name] = self.stop_service(name, timeout)
        return {"status": "ok", "results": results}


def main():
    parser = argparse.ArgumentParser(
        description="Service lifecycle manager for web testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start services")
    start_parser.add_argument("--service", action="append", required=True, help="Service command")
    start_parser.add_argument("--name", action="append", required=True, help="Service name")
    start_parser.add_argument("--port", action="append", required=True, help="Port (number, 'auto', or path)")
    start_parser.add_argument("--health-check", default="tcp", help="Health check type")
    start_parser.add_argument("--timeout", type=int, default=60, help="Startup timeout")
    start_parser.add_argument("--cwd", help="Working directory")

    stop_parser = subparsers.add_parser("stop", help="Stop services")
    stop_parser.add_argument("--name", help="Service name (omit to stop all)")
    stop_parser.add_argument("--timeout", type=int, default=10, help="Shutdown timeout")

    restart_parser = subparsers.add_parser("restart", help="Restart a service")
    restart_parser.add_argument("--name", required=True, help="Service name")
    restart_parser.add_argument("--timeout", type=int, default=60, help="Restart timeout")

    reload_parser = subparsers.add_parser("reload", help="Call reload API")
    reload_parser.add_argument("--name", required=True, help="Service name")
    reload_parser.add_argument("--reload-endpoint", required=True, help="Reload endpoint")

    wait_parser = subparsers.add_parser("wait-ready", help="Wait for health check")
    wait_parser.add_argument("--name", required=True, help="Service name")
    wait_parser.add_argument("--timeout", type=int, default=60, help="Wait timeout")

    status_parser = subparsers.add_parser("status", help="Show service status")
    status_parser.add_argument("--json", action="store_true", help="JSON output")

    logs_parser = subparsers.add_parser("logs", help="View service logs")
    logs_parser.add_argument("--name", required=True, help="Service name")
    logs_parser.add_argument("--tail", type=int, help="Number of lines")

    args = parser.parse_args()
    manager = ServiceManager()

    if args.command == "start":
        if len(args.service) != len(args.name) or len(args.service) != len(args.port):
            output_error("Mismatch: --service, --name, --port counts must match")
        
        results = {}
        for svc, name, port in zip(args.service, args.name, args.port):
            port_file = None
            if port.startswith("/") or port.startswith("./"):
                port_file = port
                port = "auto"
            result = manager.start_service(
                name=name,
                command=svc,
                port=port,
                health_check=args.health_check,
                timeout=args.timeout,
                port_file=port_file,
                cwd=args.cwd,
            )
            results[name] = result
            if result["status"] == "error":
                output_json({"status": "error", "results": results})
                sys.exit(1)
        
        output_json({"status": "ok", "results": results})

    elif args.command == "stop":
        if args.name:
            result = manager.stop_service(args.name, args.timeout)
        else:
            result = manager.stop_all(args.timeout)
        output_json(result)

    elif args.command == "restart":
        result = manager.restart_service(args.name, args.timeout)
        output_json(result)
        if result["status"] == "error":
            sys.exit(1)

    elif args.command == "reload":
        result = manager.reload_service(args.name, args.reload_endpoint)
        output_json(result)
        if result["status"] == "error":
            sys.exit(1)

    elif args.command == "wait-ready":
        result = manager.wait_ready(args.name, args.timeout)
        output_json(result)
        if result["status"] == "error":
            sys.exit(1)

    elif args.command == "status":
        result = manager.get_status()
        output_json(result)

    elif args.command == "logs":
        result = manager.get_logs(args.name, args.tail)
        if result["status"] == "error":
            output_json(result)
            sys.exit(1)
        for line in result["lines"]:
            print(line)


if __name__ == "__main__":
    main()
