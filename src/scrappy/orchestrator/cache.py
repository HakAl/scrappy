"""
Response caching for LLM API calls.

Provides both exact-match and intent-based caching to reduce API costs.
"""

from typing import Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib
import re
from .output import BaseOutputProtocol

if TYPE_CHECKING:
    from ..infrastructure.persistence import JSONPersistence

from .provider_types import LLMResponse
from ..infrastructure.persistence import JSONPersistence


class ResponseCache:
    """
    Cache for LLM responses to avoid duplicate API calls.

    Features:
    - In-memory cache with optional disk persistence
    - TTL-based expiration
    - Hash-based key generation
    - Query normalization for better cache hits
    - Intent-based caching for semantic similarity
    - Cache statistics
    """

    def __init__(
        self,
        cache_file: Optional[str] = None,
        default_ttl_hours: int = 24,
        output: Optional[BaseOutputProtocol] = None,
        auto_load: bool = False,
        persistence: Optional['JSONPersistence'] = None
    ):
        """
        Initialize response cache (dependencies only - NO file I/O by default).

        Call restore_from_disk() after construction to load cached data from disk.

        Args:
            cache_file: Path to persistent cache file (optional)
            default_ttl_hours: Default time-to-live for cache entries in hours
            output: Output interface for error reporting (optional)
            auto_load: If True, automatically load cache in constructor (for backwards compatibility)
            persistence: JSONPersistence instance for file I/O (optional, created if not provided)
        """
        self._cache: dict = {}
        self._intent_cache: dict = {}  # Separate cache for intent-based lookups
        self._stats = {
            'hits': 0,
            'misses': 0,
            'saves': 0,
            'intent_hits': 0,
            'intent_misses': 0
        }
        self.default_ttl = timedelta(hours=default_ttl_hours)
        self.cache_file = Path(cache_file) if cache_file else None
        self.output = output or self._create_default_output()

        # Create persistence layer if file path provided
        if persistence:
            self.persistence = persistence
        elif cache_file:
            self.persistence = JSONPersistence(cache_file, output=self.output)
        else:
            self.persistence = None

        # Auto-load cache if requested (for backwards compatibility)
        if auto_load and self.persistence and self.persistence.exists():
            self._load_cache()

    def restore_from_disk(self):
        """
        Restore cache from disk file.

        Call this after construction to load previously cached data.

        Returns:
            self (for method chaining)
        """
        if self.persistence and self.persistence.exists():
            self._load_cache()
        return self

    def _create_default_output(self) -> BaseOutputProtocol:
        """Create default output interface."""
        from .output import NullOutput
        return NullOutput()

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for better cache matching.

        - Converts to lowercase
        - Collapses multiple whitespace to single space
        - Strips leading/trailing whitespace
        - Removes extra punctuation spacing
        """
        # Convert to lowercase
        normalized = text.lower()
        # Collapse multiple whitespace (including newlines, tabs) to single space
        normalized = re.sub(r'\s+', ' ', normalized)
        # Strip leading/trailing whitespace
        normalized = normalized.strip()
        # Normalize punctuation spacing (remove spaces before punctuation)
        normalized = re.sub(r'\s+([.,!?;:])', r'\1', normalized)
        return normalized

    def _generate_key(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generate a unique cache key from request parameters with normalization."""
        # Normalize the prompt and system prompt for better matching
        normalized_prompt = self._normalize_text(prompt)
        normalized_system = self._normalize_text(system_prompt) if system_prompt else ''

        # Create a deterministic string representation
        key_data = f"{provider}|{model or 'default'}|{normalized_system}|{normalized_prompt}|{max_tokens}|{temperature:.2f}"
        # Hash it for consistent key length
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _generate_intent_key(
        self,
        intent: str,
        entities: dict,
        keywords: list,
        provider: str,
        model: Optional[str] = None
    ) -> str:
        """
        Generate a cache key based on intent classification.

        This allows similar queries with the same intent and entities to share cached responses.
        The key focuses on:
        - Intent type (what the user wants to do)
        - Specific entities (file names, function names, class names, etc.)
        - NOT general keywords (too variable between similar queries)
        """
        # Sort entities for deterministic key - only include specific entities
        # These are the entities that really matter for the query
        important_entity_types = ['file_path', 'function_name', 'class_name', 'error_type', 'package_name']
        sorted_entities = {}
        for key in sorted(entities.keys()):
            if key in important_entity_types:
                sorted_entities[key] = sorted(entities[key]) if isinstance(entities[key], list) else entities[key]

        # Create intent-based key (without general keywords for broader matching)
        key_data = f"{provider}|{model or 'default'}|{intent}|{json.dumps(sorted_entities, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> Optional[LLMResponse]:
        """
        Get cached response if available and not expired.

        Returns:
            LLMResponse if found and valid, None otherwise
        """
        key = self._generate_key(provider, prompt, model, system_prompt, max_tokens, temperature)

        if key not in self._cache:
            self._stats['misses'] += 1
            return None

        entry = self._cache[key]

        # Check expiration
        cached_at = datetime.fromisoformat(entry['cached_at'])
        if datetime.now() - cached_at > self.default_ttl:
            # Expired
            del self._cache[key]
            self._stats['misses'] += 1
            return None

        self._stats['hits'] += 1

        # Reconstruct LLMResponse
        return LLMResponse(
            content=entry['content'],
            model=entry['model'],
            provider=entry['provider'],
            tokens_used=entry['tokens_used'],
            input_tokens=entry.get('input_tokens', 0),
            output_tokens=entry.get('output_tokens', 0),
            latency_ms=0.0,  # Cached response has no latency
            timestamp=cached_at
        )

    def put(
        self,
        response: LLMResponse,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ):
        """Store a response in cache."""
        key = self._generate_key(response.provider, prompt, model, system_prompt, max_tokens, temperature)

        self._cache[key] = {
            'content': response.content,
            'model': response.model,
            'provider': response.provider,
            'tokens_used': response.tokens_used,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cached_at': datetime.now().isoformat()
        }

        self._stats['saves'] += 1

        # Persist if configured
        if self.persistence:
            self._save_cache()

    async def put_async(
        self,
        response: LLMResponse,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ):
        """Store a response in cache asynchronously."""
        key = self._generate_key(response.provider, prompt, model, system_prompt, max_tokens, temperature)

        self._cache[key] = {
            'content': response.content,
            'model': response.model,
            'provider': response.provider,
            'tokens_used': response.tokens_used,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cached_at': datetime.now().isoformat()
        }

        self._stats['saves'] += 1

        # Persist if configured (non-blocking)
        if self.persistence:
            await self._save_cache_async()

    def get_by_intent(
        self,
        intent: str,
        entities: dict,
        keywords: list,
        provider: str,
        model: Optional[str] = None
    ) -> Optional[LLMResponse]:
        """
        Get cached response by intent classification.

        This provides semantic matching - queries with same intent and entities
        can share cached responses even if exact wording differs.

        Args:
            intent: The classified intent (e.g., 'code_search', 'bug_investigation')
            entities: Extracted entities (e.g., {'file_path': ['main.py'], 'function_name': ['foo']})
            keywords: Important keywords from the query
            provider: LLM provider name
            model: Model name (optional)

        Returns:
            LLMResponse if found and valid, None otherwise
        """
        key = self._generate_intent_key(intent, entities, keywords, provider, model)

        if key not in self._intent_cache:
            self._stats['intent_misses'] += 1
            return None

        entry = self._intent_cache[key]

        # Check expiration
        cached_at = datetime.fromisoformat(entry['cached_at'])
        if datetime.now() - cached_at > self.default_ttl:
            # Expired
            del self._intent_cache[key]
            self._stats['intent_misses'] += 1
            return None

        self._stats['intent_hits'] += 1

        # Reconstruct LLMResponse
        return LLMResponse(
            content=entry['content'],
            model=entry['model'],
            provider=entry['provider'],
            tokens_used=entry['tokens_used'],
            input_tokens=entry.get('input_tokens', 0),
            output_tokens=entry.get('output_tokens', 0),
            latency_ms=0.0,  # Cached response has no latency
            timestamp=cached_at
        )

    def put_by_intent(
        self,
        response: LLMResponse,
        intent: str,
        entities: dict,
        keywords: list
    ):
        """
        Store a response in intent-based cache.

        Args:
            response: The LLM response to cache
            intent: The classified intent
            entities: Extracted entities from the query
            keywords: Important keywords from the query
        """
        key = self._generate_intent_key(intent, entities, keywords, response.provider, response.model)

        self._intent_cache[key] = {
            'content': response.content,
            'model': response.model,
            'provider': response.provider,
            'tokens_used': response.tokens_used,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cached_at': datetime.now().isoformat(),
            'intent': intent,
            'entities': entities,
            'keywords': keywords
        }

        # Persist if configured
        if self.persistence:
            self._save_cache()

    async def put_by_intent_async(
        self,
        response: LLMResponse,
        intent: str,
        entities: dict,
        keywords: list
    ):
        """
        Store a response in intent-based cache asynchronously.

        Args:
            response: The LLM response to cache
            intent: The classified intent
            entities: Extracted entities from the query
            keywords: Important keywords from the query
        """
        key = self._generate_intent_key(intent, entities, keywords, response.provider, response.model)

        self._intent_cache[key] = {
            'content': response.content,
            'model': response.model,
            'provider': response.provider,
            'tokens_used': response.tokens_used,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cached_at': datetime.now().isoformat(),
            'intent': intent,
            'entities': entities,
            'keywords': keywords
        }

        # Persist if configured (non-blocking)
        if self.persistence:
            await self._save_cache_async()

    def _save_cache(self):
        """Save cache to disk."""
        if not self.persistence:
            return

        # Save both exact match and intent caches
        cache_data = {
            'exact': self._cache,
            'intent': self._intent_cache
        }
        self.persistence.save(cache_data)

    async def _save_cache_async(self):
        """Save cache to disk asynchronously."""
        if not self.persistence:
            return

        # Save both exact match and intent caches
        cache_data = {
            'exact': self._cache,
            'intent': self._intent_cache
        }
        await self.persistence.save_async(cache_data)

    def _load_cache(self):
        """Load cache from disk."""
        if not self.persistence:
            return

        cache_data = self.persistence.load()

        if cache_data is None:
            self._cache = {}
            self._intent_cache = {}
            return

        # Handle both old format (dict) and new format (nested dicts)
        if isinstance(cache_data, dict) and 'exact' in cache_data:
            self._cache = cache_data.get('exact', {})
            self._intent_cache = cache_data.get('intent', {})
        else:
            # Old format - treat as exact cache only
            self._cache = cache_data
            self._intent_cache = {}

        # Clean expired entries on load
        self._cleanup_expired()

    async def _load_cache_async(self):
        """Load cache from disk asynchronously."""
        if not self.persistence:
            return

        cache_data = await self.persistence.load_async()

        if cache_data is None:
            self._cache = {}
            self._intent_cache = {}
            return

        # Handle both old format (dict) and new format (nested dicts)
        if isinstance(cache_data, dict) and 'exact' in cache_data:
            self._cache = cache_data.get('exact', {})
            self._intent_cache = cache_data.get('intent', {})
        else:
            # Old format - treat as exact cache only
            self._cache = cache_data
            self._intent_cache = {}

        # Clean expired entries on load
        self._cleanup_expired()

    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        now = datetime.now()

        # Clean exact match cache
        expired_keys = []
        for key, entry in self._cache.items():
            try:
                cached_at = datetime.fromisoformat(entry['cached_at'])
                if now - cached_at > self.default_ttl:
                    expired_keys.append(key)
            except Exception:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]

        # Clean intent cache
        expired_intent_keys = []
        for key, entry in self._intent_cache.items():
            try:
                cached_at = datetime.fromisoformat(entry['cached_at'])
                if now - cached_at > self.default_ttl:
                    expired_intent_keys.append(key)
            except Exception:
                expired_intent_keys.append(key)

        for key in expired_intent_keys:
            del self._intent_cache[key]

    def clear(self):
        """Clear all cache entries."""
        self._cache = {}
        self._intent_cache = {}
        if self.persistence:
            self.persistence.clear()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'saves': 0,
            'intent_hits': 0,
            'intent_misses': 0
        }

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_exact = self._stats['hits'] + self._stats['misses']
        exact_hit_rate = (self._stats['hits'] / total_exact * 100) if total_exact > 0 else 0

        total_intent = self._stats['intent_hits'] + self._stats['intent_misses']
        intent_hit_rate = (self._stats['intent_hits'] / total_intent * 100) if total_intent > 0 else 0

        return {
            'exact_cache_entries': len(self._cache),
            'intent_cache_entries': len(self._intent_cache),
            'exact_hits': self._stats['hits'],
            'exact_misses': self._stats['misses'],
            'exact_hit_rate': f"{exact_hit_rate:.1f}%",
            'intent_hits': self._stats['intent_hits'],
            'intent_misses': self._stats['intent_misses'],
            'intent_hit_rate': f"{intent_hit_rate:.1f}%",
            'saves': self._stats['saves'],
            'cache_file': str(self.cache_file) if self.cache_file else 'memory only'
        }

    def invalidate(
        self,
        provider: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> int:
        """
        Invalidate specific cache entries.

        Args:
            provider: Provider name to filter by (None for all providers)
            prompt: Prompt substring to filter by (None for all prompts)

        Returns:
            Number of entries invalidated
        """
        count = 0

        # Build filter function based on provided criteria
        def matches_criteria(entry: dict) -> bool:
            if provider is not None and entry.get('provider') != provider:
                return False
            # Note: We can't filter by prompt directly since we only store hashed keys
            # For prompt filtering, we'd need to store the original prompt
            return True

        # Invalidate from exact cache
        keys_to_remove = [
            key for key, entry in self._cache.items()
            if matches_criteria(entry)
        ]
        for key in keys_to_remove:
            del self._cache[key]
            count += 1

        # Invalidate from intent cache
        intent_keys_to_remove = [
            key for key, entry in self._intent_cache.items()
            if matches_criteria(entry)
        ]
        for key in intent_keys_to_remove:
            del self._intent_cache[key]
            count += 1

        if self.persistence and count > 0:
            self._save_cache()

        return count

    def invalidate_provider(self, provider: str) -> int:
        """
        Invalidate all cache entries for a specific provider.

        Args:
            provider: Provider name to invalidate

        Returns:
            Number of entries invalidated
        """
        return self.invalidate(provider=provider)
