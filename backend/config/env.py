"""Typed readers for settings that come from environment variables.

Misconfiguration fails at startup with a clear message instead of surfacing later as odd behaviour.
"""

import os

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _read(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def env_str(name: str, default: str | None = None) -> str:
    """Return the variable, or ``default``. Without a default the variable is required."""
    value = _read(name)
    if value is not None:
        return value
    if default is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return default


def env_bool(name: str, default: bool) -> bool:
    value = _read(name)
    if value is None:
        return default
    if value.lower() in _TRUE:
        return True
    if value.lower() in _FALSE:
        return False
    raise ImproperlyConfigured(f"Environment variable {name} must be true or false, got {value!r}.")


def env_list(name: str, default: list[str]) -> list[str]:
    """Comma-separated list; blank items are dropped."""
    value = _read(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]
