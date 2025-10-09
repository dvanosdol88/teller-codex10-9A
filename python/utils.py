"""Shared helpers for Falcon resources."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any


def to_serializable(value: Any):
    """Convert SQLAlchemy values to JSON serializable data."""

    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_serializable(v) for v in value]
    return value


def ensure_json_serializable(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: ensure_json_serializable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [ensure_json_serializable(v) for v in data]
    return to_serializable(data)
