from __future__ import annotations
import logging
import sys
import json
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    SKIP_FIELDS = {
        "args", "asctime", "created", "exc_info", "exc_text",
        "filename", "funcName", "id", "levelname", "levelno",
        "lineno", "module", "msecs", "message", "msg", "name",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName",
        "timestamp", "level", "logger", "service", "agent"
    }

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
            "agent": getattr(record, "agent", None),
            "task_id": getattr(record, "task_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in self.SKIP_FIELDS:
                log_obj[key] = value
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)

    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = service_name
        return record

    logging.setLogRecordFactory(record_factory)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
