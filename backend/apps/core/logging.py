"""JSON log formatting: one object per line, so log platforms can index and query every field."""

import json
import logging
from datetime import UTC, datetime

# Attributes every LogRecord has. Anything else was passed with `extra=` and becomes a top-level field.
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        entry = {
            "ts": timestamp.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        # default=str keeps logging from ever failing on a value json can't encode.
        return json.dumps(entry, default=str)
