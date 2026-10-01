"""Normalisation shared by every place that stores a task name, so requests and episodes always match."""

import re

_WHITESPACE = re.compile(r"\s+")


def normalise_task_name(value: str) -> str:
    """`"  Pick   CUP "` -> `"pick cup"`."""
    return _WHITESPACE.sub(" ", value).strip().lower()
