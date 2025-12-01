"""
JSON formatting utilities for structured logging.

Provides safe JSON serialization that handles non-serializable types
gracefully without crashing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class SafeJSONEncoder(json.JSONEncoder):
    """
    JSON encoder that handles non-serializable types gracefully.

    Converts common non-serializable types to their string representations:
    - datetime objects -> ISO format strings
    - bytes -> UTF-8 decoded string or byte count
    - sets -> lists
    - Path objects -> strings
    - callables -> function name strings
    - custom objects -> class name strings
    """

    def default(self, obj):
        """Convert non-serializable objects to string representations."""
        # Handle datetime objects
        if isinstance(obj, datetime):
            return obj.isoformat()

        # Handle bytes
        if isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return f"<bytes: {len(obj)} bytes>"

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)

        # Handle functions/callables
        if callable(obj):
            return f"<{type(obj).__name__}: {getattr(obj, '__name__', 'anonymous')}>"

        # Handle objects with __dict__
        if hasattr(obj, '__dict__'):
            return f"<{type(obj).__name__}>"

        # Fallback: convert to string
        try:
            return str(obj)
        except Exception:
            return f"<non-serializable: {type(obj).__name__}>"


def safe_json_dumps(obj: Any, indent: Optional[int] = None) -> str:
    """
    Safely serialize object to JSON string, handling non-serializable types.

    Args:
        obj: Object to serialize
        indent: Optional indentation level for pretty printing

    Returns:
        JSON string representation of the object
    """
    try:
        return json.dumps(obj, cls=SafeJSONEncoder, indent=indent)
    except Exception as e:
        # Last resort fallback if even the custom encoder fails
        return json.dumps({
            "error": "serialization_failed",
            "error_message": str(e),
            "type": str(type(obj))
        })
