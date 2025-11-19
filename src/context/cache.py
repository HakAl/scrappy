"""
Context caching for persistence between sessions.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ContextCache:
    """
    Handles persistence of codebase context to disk.

    Usage:
        cache = ContextCache()
        cache.save(cache_file, {'explored_at': datetime.now(), ...})
        data = cache.load(cache_file)
    """

    # Keys that should be treated as datetime fields
    DATETIME_FIELDS = {'explored_at'}

    def save(self, cache_file, data: dict) -> None:
        """
        Save context data to disk cache.

        Args:
            cache_file: Path to cache file (string or Path object)
            data: Dictionary of context data to save
        """
        cache_file = Path(cache_file)

        try:
            # Create parent directories if needed
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Prepare data for serialization
            serializable_data = self._prepare_for_save(data)

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, indent=2)
        except Exception:
            pass  # Caching is optional, don't raise errors

    def load(self, cache_file) -> Optional[dict]:
        """
        Load context data from disk cache.

        Args:
            cache_file: Path to cache file (string or Path object)

        Returns:
            Loaded data dictionary, or None if file doesn't exist or is invalid
        """
        cache_file = Path(cache_file)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    return None
                data = json.loads(content)

            # Restore datetime fields
            return self._prepare_after_load(data)
        except (json.JSONDecodeError, Exception):
            return None

    def clear(self, cache_file) -> None:
        """
        Clear the cached context file.

        Args:
            cache_file: Path to cache file (string or Path object)
        """
        cache_file = Path(cache_file)

        if cache_file.exists():
            cache_file.unlink()

    def _prepare_for_save(self, data: dict) -> dict:
        """
        Prepare data for JSON serialization.

        Converts datetime objects to ISO format strings.
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._prepare_for_save(value)
            elif isinstance(value, list):
                result[key] = [
                    self._prepare_for_save(item) if isinstance(item, dict)
                    else item.isoformat() if isinstance(item, datetime)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _prepare_after_load(self, data: dict) -> dict:
        """
        Restore data after JSON deserialization.

        Converts ISO format strings back to datetime objects for known fields.
        """
        result = {}
        for key, value in data.items():
            if key in self.DATETIME_FIELDS and value is not None:
                # Try to parse as datetime
                if isinstance(value, str):
                    try:
                        result[key] = datetime.fromisoformat(value)
                    except ValueError:
                        # Keep as string if not a valid datetime
                        result[key] = value
                else:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self._prepare_after_load(value)
            elif isinstance(value, list):
                result[key] = [
                    self._prepare_after_load(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
