"""
LLM Agent Orchestrator

This module provides the coordination layer for multi-provider LLM agent teams.

Architecture:
    Claude Code (complex reasoning) <-- Human/Orchestrator
           |
           v
    Orchestrator (this module)
           |
    +------+------+------+
    |      |      |      |
    v      v      v      v
   Groq  Cohere  [Future providers...]
  (fast) (embed) (OpenRouter, HuggingFace, etc.)

The orchestrator:
1. Maintains a registry of available providers
2. Routes tasks to appropriate providers based on task type
3. Tracks usage and rate limits across providers
4. Provides fallback strategies when limits are hit
"""

from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib

try:
    from .providers import ProviderRegistry, GroqProvider, CohereProvider, GeminiProvider, CerebrasProvider, LLMResponse
    from .context import CodebaseContext
except ImportError:
    # Allow running as script
    from providers import ProviderRegistry, GroqProvider, CohereProvider, GeminiProvider, CerebrasProvider, LLMResponse
    from context import CodebaseContext


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

    def __init__(self, cache_file: Optional[str] = None, default_ttl_hours: int = 24):
        """
        Initialize response cache.

        Args:
            cache_file: Path to persistent cache file (optional)
            default_ttl_hours: Default time-to-live for cache entries in hours
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

        # Load persistent cache if available
        if self.cache_file and self.cache_file.exists():
            self._load_cache()

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for better cache matching.

        - Converts to lowercase
        - Collapses multiple whitespace to single space
        - Strips leading/trailing whitespace
        - Removes extra punctuation spacing
        """
        import re
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
        import json
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
        if self.cache_file:
            self._save_cache()

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
        if self.cache_file:
            self._save_cache()

    def _save_cache(self):
        """Save cache to disk."""
        try:
            # Save both exact match and intent caches
            cache_data = {
                'exact': self._cache,
                'intent': self._intent_cache
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass  # Silently fail on write errors

    def _load_cache(self):
        """Load cache from disk."""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

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
        except Exception:
            self._cache = {}
            self._intent_cache = {}

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
        if self.cache_file and self.cache_file.exists():
            self.cache_file.unlink()
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

    def invalidate_provider(self, provider: str):
        """Invalidate all cache entries for a specific provider."""
        # Invalidate from exact cache
        keys_to_remove = [
            key for key, entry in self._cache.items()
            if entry.get('provider') == provider
        ]
        for key in keys_to_remove:
            del self._cache[key]

        # Invalidate from intent cache
        intent_keys_to_remove = [
            key for key, entry in self._intent_cache.items()
            if entry.get('provider') == provider
        ]
        for key in intent_keys_to_remove:
            del self._intent_cache[key]

        if self.cache_file:
            self._save_cache()


class RateLimitTracker:
    """
    Persistent rate limit tracking for LLM providers.

    Features:
    - Tracks requests and tokens per provider/model
    - Persists to disk for tracking across sessions
    - Automatic reset for daily/monthly limits
    - Proactive quota monitoring
    """

    def __init__(self, tracker_file: Optional[str] = None):
        """
        Initialize rate limit tracker.

        Args:
            tracker_file: Path to persistent tracker file (optional)
        """
        self._usage: dict = {}
        self.tracker_file = Path(tracker_file) if tracker_file else None

        # Load existing data if available
        if self.tracker_file and self.tracker_file.exists():
            self._load_tracker()
        else:
            self._initialize_empty()

    def _initialize_empty(self):
        """Initialize empty tracking structure."""
        self._usage = {
            'providers': {},  # provider -> model -> usage data
            'last_reset': {
                'daily': datetime.now().date().isoformat(),
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': datetime.now().isoformat()
        }

    def _load_tracker(self):
        """Load tracker data from disk."""
        try:
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                self._usage = json.load(f)

            # Check for resets needed
            self._check_and_reset()
        except Exception:
            self._initialize_empty()

    def _save_tracker(self):
        """Save tracker data to disk."""
        if not self.tracker_file:
            return

        try:
            with open(self.tracker_file, 'w', encoding='utf-8') as f:
                json.dump(self._usage, f, indent=2)
        except Exception:
            pass  # Silently fail on write errors

    def _check_and_reset(self):
        """Check if daily or monthly resets are needed."""
        current_date = datetime.now().date().isoformat()
        current_month = datetime.now().strftime('%Y-%m')

        needs_save = False

        # Check daily reset
        if self._usage.get('last_reset', {}).get('daily') != current_date:
            self._reset_daily_limits()
            self._usage['last_reset']['daily'] = current_date
            needs_save = True

        # Check monthly reset
        if self._usage.get('last_reset', {}).get('monthly') != current_month:
            self._reset_monthly_limits()
            self._usage['last_reset']['monthly'] = current_month
            needs_save = True

        if needs_save:
            self._save_tracker()

    def _reset_daily_limits(self):
        """Reset daily request and token counters."""
        for provider_data in self._usage.get('providers', {}).values():
            for model_data in provider_data.values():
                model_data['requests_today'] = 0
                model_data['tokens_today'] = 0
                model_data['input_tokens_today'] = 0
                model_data['output_tokens_today'] = 0

    def _reset_monthly_limits(self):
        """Reset monthly request counters."""
        for provider_data in self._usage.get('providers', {}).values():
            for model_data in provider_data.values():
                model_data['requests_this_month'] = 0
                model_data['tokens_this_month'] = 0

    def _ensure_provider_model(self, provider: str, model: str):
        """Ensure tracking structure exists for provider/model."""
        if 'providers' not in self._usage:
            self._usage['providers'] = {}

        if provider not in self._usage['providers']:
            self._usage['providers'][provider] = {}

        if model not in self._usage['providers'][provider]:
            self._usage['providers'][provider][model] = {
                'requests_today': 0,
                'requests_this_month': 0,
                'tokens_today': 0,
                'tokens_this_month': 0,
                'input_tokens_today': 0,
                'output_tokens_today': 0,
                'total_requests': 0,
                'total_tokens': 0,
                'last_request': None,
                'errors': []
            }

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        Record a completed API request.

        Args:
            provider: Provider name
            model: Model used
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            success: Whether request succeeded
            error_message: Error message if failed
        """
        # Check for resets first
        self._check_and_reset()

        self._ensure_provider_model(provider, model)
        model_data = self._usage['providers'][provider][model]

        total_tokens = input_tokens + output_tokens

        # Update counters
        model_data['requests_today'] += 1
        model_data['requests_this_month'] += 1
        model_data['total_requests'] += 1

        model_data['tokens_today'] += total_tokens
        model_data['tokens_this_month'] += total_tokens
        model_data['total_tokens'] += total_tokens

        model_data['input_tokens_today'] += input_tokens
        model_data['output_tokens_today'] += output_tokens

        model_data['last_request'] = datetime.now().isoformat()

        # Track errors
        if not success and error_message:
            model_data['errors'].append({
                'timestamp': datetime.now().isoformat(),
                'message': error_message[:200]  # Truncate long errors
            })
            # Keep only last 10 errors
            model_data['errors'] = model_data['errors'][-10:]

        self._save_tracker()

    def get_usage(self, provider: str, model: Optional[str] = None) -> dict:
        """
        Get current usage for a provider/model.

        Args:
            provider: Provider name
            model: Specific model (optional, returns all models if not specified)

        Returns:
            Usage statistics dict
        """
        self._check_and_reset()

        if provider not in self._usage.get('providers', {}):
            return {}

        if model:
            return self._usage['providers'][provider].get(model, {})

        return self._usage['providers'][provider]

    def get_remaining_quota(self, provider: str, model: str, limits: 'ProviderLimits') -> dict:
        """
        Calculate remaining quota for a provider/model.

        Args:
            provider: Provider name
            model: Model name
            limits: ProviderLimits from provider

        Returns:
            Dict with remaining requests and tokens
        """
        self._check_and_reset()
        self._ensure_provider_model(provider, model)

        usage = self._usage['providers'][provider][model]

        remaining = {
            'requests_remaining_today': None,
            'requests_remaining_month': None,
            'tokens_remaining_today': None,
            'tokens_remaining_minute': None,
            'usage_today': usage['requests_today'],
            'tokens_today': usage['tokens_today'],
            'usage_this_month': usage['requests_this_month']
        }

        # Calculate remaining based on limits
        if limits.requests_per_day:
            remaining['requests_remaining_today'] = max(0, limits.requests_per_day - usage['requests_today'])

        if limits.requests_per_month:
            remaining['requests_remaining_month'] = max(0, limits.requests_per_month - usage['requests_this_month'])

        if limits.tokens_per_day:
            remaining['tokens_remaining_today'] = max(0, limits.tokens_per_day - usage['tokens_today'])

        if limits.tokens_per_minute:
            remaining['tokens_remaining_minute'] = limits.tokens_per_minute  # Can't track minute-level precisely

        return remaining

    def is_limit_approaching(self, provider: str, model: str, limits: 'ProviderLimits', threshold: float = 0.1) -> dict:
        """
        Check if approaching rate limits (within threshold of limit).

        Args:
            provider: Provider name
            model: Model name
            limits: ProviderLimits from provider
            threshold: Warning threshold (0.1 = warn at 90% usage)

        Returns:
            Dict with warning flags
        """
        remaining = self.get_remaining_quota(provider, model, limits)
        warnings = {
            'approaching_daily_request_limit': False,
            'approaching_monthly_request_limit': False,
            'approaching_daily_token_limit': False,
            'message': None
        }

        messages = []

        if limits.requests_per_day and remaining['requests_remaining_today'] is not None:
            if remaining['requests_remaining_today'] <= limits.requests_per_day * threshold:
                warnings['approaching_daily_request_limit'] = True
                messages.append(f"Only {remaining['requests_remaining_today']} requests remaining today")

        if limits.requests_per_month and remaining['requests_remaining_month'] is not None:
            if remaining['requests_remaining_month'] <= limits.requests_per_month * threshold:
                warnings['approaching_monthly_request_limit'] = True
                messages.append(f"Only {remaining['requests_remaining_month']} requests remaining this month")

        if limits.tokens_per_day and remaining['tokens_remaining_today'] is not None:
            if remaining['tokens_remaining_today'] <= limits.tokens_per_day * threshold:
                warnings['approaching_daily_token_limit'] = True
                messages.append(f"Only {remaining['tokens_remaining_today']} tokens remaining today")

        if messages:
            warnings['message'] = f"{provider}/{model}: " + ", ".join(messages)

        return warnings

    def get_all_usage_summary(self) -> dict:
        """Get summary of all provider usage."""
        self._check_and_reset()

        summary = {
            'last_reset': self._usage.get('last_reset', {}),
            'providers': {}
        }

        for provider, models in self._usage.get('providers', {}).items():
            summary['providers'][provider] = {
                'total_requests_today': sum(m.get('requests_today', 0) for m in models.values()),
                'total_tokens_today': sum(m.get('tokens_today', 0) for m in models.values()),
                'total_requests_month': sum(m.get('requests_this_month', 0) for m in models.values()),
                'models': list(models.keys()),
                'by_model': {
                    model: {
                        'requests_today': data.get('requests_today', 0),
                        'tokens_today': data.get('tokens_today', 0),
                        'last_request': data.get('last_request')
                    }
                    for model, data in models.items()
                }
            }

        return summary

    def clear(self):
        """Clear all tracking data."""
        self._initialize_empty()
        if self.tracker_file and self.tracker_file.exists():
            self.tracker_file.unlink()

    def reset_provider(self, provider: str):
        """Reset usage for a specific provider."""
        if provider in self._usage.get('providers', {}):
            del self._usage['providers'][provider]
            self._save_tracker()


class AgentOrchestrator:
    """
    Central coordinator for multi-provider LLM agent team.

    Usage with Claude Code as reasoning layer:
        # In Claude Code session:
        orch = AgentOrchestrator()

        # Delegate simple task to Groq
        result = orch.delegate('groq', 'Summarize this text: ...')

        # Use Cohere for embeddings
        embeddings = orch.providers.get('cohere').embed(['text1', 'text2'])

        # Claude (you) handles complex reasoning, then delegates sub-tasks
    """

    def __init__(
        self,
        auto_register: bool = True,
        orchestrator_provider: Optional[str] = None,
        project_path: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        enable_cache: bool = True,
        cache_ttl_hours: int = 24
    ):
        """
        Initialize orchestrator.

        Args:
            auto_register: Automatically register available providers
            orchestrator_provider: Provider to use as the "brain" for planning/reasoning
                                  (default: 'cerebras' if available, else first available)
            project_path: Path to project for context awareness (default: current dir)
            auto_explore: Automatically explore codebase on init
            context_aware: Enable context-augmented prompts
            enable_cache: Enable response caching to avoid duplicate API calls
            cache_ttl_hours: Time-to-live for cache entries in hours
        """
        self.registry = ProviderRegistry()
        self.task_history: list[dict] = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = orchestrator_provider
        self.context_aware = context_aware
        self.caching_enabled = enable_cache

        # Initialize codebase context
        self.context = CodebaseContext(project_path)

        # Initialize response cache
        cache_file = str(self.context.project_path / ".llm_response_cache.json")
        self.cache = ResponseCache(cache_file=cache_file, default_ttl_hours=cache_ttl_hours)

        # Initialize persistent rate limit tracker
        rate_limit_file = str(self.context.project_path / ".llm_rate_limits.json")
        self.rate_tracker = RateLimitTracker(tracker_file=rate_limit_file)

        # Initialize session working memory (ephemeral, not persisted)
        self.working_memory = {
            'file_reads': {},       # path -> {'content': str, 'timestamp': datetime, 'lines': int}
            'search_results': [],   # list of {'query': str, 'results': list, 'timestamp': datetime}
            'git_operations': [],   # list of {'operation': str, 'output': str, 'timestamp': datetime}
            'discoveries': [],      # list of {'finding': str, 'location': str, 'timestamp': datetime}
            'max_file_cache': 20,   # LRU cache size for file reads
            'max_searches': 10,     # Keep last N searches
            'max_git_ops': 10,      # Keep last N git operations
        }

        if auto_register:
            self._auto_register_providers()
            self._setup_brain(orchestrator_provider)

        # Auto-explore if requested and providers are available
        if auto_explore and self._brain:
            self._auto_explore()

    def _auto_register_providers(self):
        """Attempt to register all known providers."""
        # Try Cerebras (primary - highest quota)
        try:
            self.registry.register(CerebrasProvider())
            print("[OK] Cerebras provider registered (14,400 RPD)")
        except Exception as e:
            print(f"[X] Cerebras provider unavailable: {e}")

        # Try Groq (secondary)
        try:
            self.registry.register(GroqProvider())
            print("[OK] Groq provider registered (7,000 RPD)")
        except Exception as e:
            print(f"[X] Groq provider unavailable: {e}")

        # Try Gemini (with auto-fallback)
        try:
            self.registry.register(GeminiProvider())
            print("[OK] Gemini provider registered (auto-fallback enabled)")
        except Exception as e:
            print(f"[X] Gemini provider unavailable: {e}")

        # Try Cohere (limited - embeddings only)
        try:
            self.registry.register(CohereProvider())
            print("[OK] Cohere provider registered (1,000/month - use sparingly)")
        except Exception as e:
            print(f"[X] Cohere provider unavailable: {e}")

    def _setup_brain(self, preferred_provider: Optional[str] = None):
        """
        Set up the orchestrator's reasoning brain.

        Priority: specified > cerebras > groq > gemini > any available
        """
        available = self.registry.list_available()

        if not available:
            print("[WARN] No providers available for orchestrator brain")
            return

        # Use specified provider if available
        if preferred_provider and preferred_provider in available:
            self._brain = self.registry.get(preferred_provider)
            self._brain_name = preferred_provider
            print(f"[BRAIN] Using {preferred_provider} as orchestrator brain")
            return

        # Default priority: cerebras > groq > gemini
        priority = ['cerebras', 'groq', 'gemini']
        for provider in priority:
            if provider in available:
                self._brain = self.registry.get(provider)
                self._brain_name = provider
                print(f"[BRAIN] Using {provider} as orchestrator brain")
                return

        # Fallback to first available
        self._brain_name = available[0]
        self._brain = self.registry.get(self._brain_name)
        print(f"[BRAIN] Using {self._brain_name} as orchestrator brain (fallback)")

    def _auto_explore(self):
        """Automatically explore the codebase if not already explored."""
        if self.context.is_explored():
            print(f"[CONTEXT] Loaded cached context for {self.context.project_path.name}")
            return

        print(f"[CONTEXT] Exploring codebase: {self.context.project_path}")
        result = self.context.explore()

        if result['status'] == 'explored':
            print(f"[CONTEXT] Found {result['total_files']} files")

            # Generate summary using brain
            def llm_summary(prompt):
                response = self.brain_provider.chat(
                    messages=[
                        {'role': 'system', 'content': 'You are a code analyst. Provide concise technical summaries.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    max_tokens=500,
                    temperature=0.3
                )
                self.task_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'provider': self._brain_name,
                    'model': response.model,
                    'tokens_used': response.tokens_used,
                    'latency_ms': response.latency_ms,
                    'task_type': 'context_analysis',
                })
                return response.content

            self.context.generate_summary(llm_summary)
            print(f"[CONTEXT] Generated project summary")

    def explore_project(self, force: bool = False) -> dict:
        """
        Manually trigger project exploration.

        Args:
            force: Force re-exploration even if cached

        Returns:
            Exploration result dict
        """
        if force:
            self.context.clear_cache()

        result = self.context.explore(force=force)

        # Generate or regenerate summary
        if result['status'] == 'explored' or force:
            def llm_summary(prompt):
                response = self.brain_provider.chat(
                    messages=[
                        {'role': 'system', 'content': 'You are a code analyst. Provide concise technical summaries.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    max_tokens=500,
                    temperature=0.3
                )
                self.task_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'provider': self._brain_name,
                    'model': response.model,
                    'tokens_used': response.tokens_used,
                    'latency_ms': response.latency_ms,
                    'task_type': 'context_analysis',
                })
                return response.content

            self.context.generate_summary(llm_summary)

        return result

    def get_context_status(self) -> dict:
        """Get current codebase context status."""
        return self.context.get_status()

    # Working Memory Management Methods
    def remember_file_read(self, path: str, content: str, lines: int = 0):
        """Store a file read in working memory (LRU cache)."""
        self.working_memory['file_reads'][path] = {
            'content': content,
            'timestamp': datetime.now(),
            'lines': lines
        }
        # Enforce LRU cache size
        max_cache = self.working_memory['max_file_cache']
        if len(self.working_memory['file_reads']) > max_cache:
            # Remove oldest entry
            oldest_path = min(
                self.working_memory['file_reads'].keys(),
                key=lambda p: self.working_memory['file_reads'][p]['timestamp']
            )
            del self.working_memory['file_reads'][oldest_path]

    def remember_search(self, query: str, results: list):
        """Store a search result in working memory."""
        self.working_memory['search_results'].append({
            'query': query,
            'results': results,
            'timestamp': datetime.now()
        })
        # Keep only last N searches
        max_searches = self.working_memory['max_searches']
        if len(self.working_memory['search_results']) > max_searches:
            self.working_memory['search_results'] = self.working_memory['search_results'][-max_searches:]

    def remember_git_operation(self, operation: str, output: str):
        """Store a git operation result in working memory."""
        self.working_memory['git_operations'].append({
            'operation': operation,
            'output': output,
            'timestamp': datetime.now()
        })
        # Keep only last N operations
        max_ops = self.working_memory['max_git_ops']
        if len(self.working_memory['git_operations']) > max_ops:
            self.working_memory['git_operations'] = self.working_memory['git_operations'][-max_ops:]

    def add_discovery(self, finding: str, location: str = ""):
        """Add a discovery/learning to working memory."""
        self.working_memory['discoveries'].append({
            'finding': finding,
            'location': location,
            'timestamp': datetime.now()
        })

    def get_working_memory_summary(self) -> dict:
        """Get a summary of current working memory state."""
        return {
            'files_cached': len(self.working_memory['file_reads']),
            'cached_files': list(self.working_memory['file_reads'].keys()),
            'recent_searches': len(self.working_memory['search_results']),
            'git_operations': len(self.working_memory['git_operations']),
            'discoveries': len(self.working_memory['discoveries']),
        }

    def get_working_memory_context(self) -> str:
        """Build context string from working memory for LLM augmentation."""
        parts = []

        # Recent file reads (just paths and line counts, not full content)
        if self.working_memory['file_reads']:
            files_info = []
            for path, info in self.working_memory['file_reads'].items():
                files_info.append(f"  - {path} ({info['lines']} lines)")
            parts.append("Recently accessed files:\n" + "\n".join(files_info))

        # Recent searches
        if self.working_memory['search_results']:
            searches_info = []
            for search in self.working_memory['search_results'][-3:]:  # Last 3 searches
                result_count = len(search['results']) if isinstance(search['results'], list) else 0
                searches_info.append(f"  - '{search['query']}' ({result_count} results)")
            parts.append("Recent searches:\n" + "\n".join(searches_info))

        # Recent git operations
        if self.working_memory['git_operations']:
            git_info = []
            for op in self.working_memory['git_operations'][-3:]:  # Last 3 ops
                git_info.append(f"  - {op['operation']}")
            parts.append("Recent git operations:\n" + "\n".join(git_info))

        # Discoveries
        if self.working_memory['discoveries']:
            disc_info = []
            for disc in self.working_memory['discoveries'][-5:]:  # Last 5 discoveries
                loc = f" at {disc['location']}" if disc['location'] else ""
                disc_info.append(f"  - {disc['finding']}{loc}")
            parts.append("Key discoveries:\n" + "\n".join(disc_info))

        if parts:
            return "[Session Working Memory]\n" + "\n\n".join(parts)
        return ""

    def clear_working_memory(self):
        """Clear all working memory (useful for resetting session state)."""
        self.working_memory['file_reads'] = {}
        self.working_memory['search_results'] = []
        self.working_memory['git_operations'] = []
        self.working_memory['discoveries'] = []

    def save_session(self, conversation_history: list = None) -> str:
        """Save current session (working memory + conversation) to disk for resume.

        Args:
            conversation_history: Optional list of conversation messages to save
        """
        session_file = str(self.context.project_path / ".llm_team_session.json")

        # Convert datetime objects to ISO strings for JSON serialization
        serializable_memory = {
            'file_reads': {},
            'search_results': [],
            'git_operations': [],
            'discoveries': [],
            'conversation_history': conversation_history or [],
            'saved_at': datetime.now().isoformat(),
            'session_start': self.created_at.isoformat(),
        }

        # Serialize file reads
        for path, info in self.working_memory['file_reads'].items():
            serializable_memory['file_reads'][path] = {
                'content': info['content'],
                'timestamp': info['timestamp'].isoformat(),
                'lines': info['lines']
            }

        # Serialize search results
        for search in self.working_memory['search_results']:
            serializable_memory['search_results'].append({
                'query': search['query'],
                'results': search['results'],
                'timestamp': search['timestamp'].isoformat()
            })

        # Serialize git operations
        for op in self.working_memory['git_operations']:
            serializable_memory['git_operations'].append({
                'operation': op['operation'],
                'output': op['output'],
                'timestamp': op['timestamp'].isoformat()
            })

        # Serialize discoveries
        for disc in self.working_memory['discoveries']:
            serializable_memory['discoveries'].append({
                'finding': disc['finding'],
                'location': disc['location'],
                'timestamp': disc['timestamp'].isoformat()
            })

        # Save task history too
        serializable_memory['task_history'] = self.task_history

        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_memory, f, indent=2)
            return session_file
        except Exception as e:
            raise RuntimeError(f"Failed to save session: {e}")

    def load_session(self) -> dict:
        """Load previous session from disk."""
        session_file = self.context.project_path / ".llm_team_session.json"

        if not session_file.exists():
            return {'status': 'no_session', 'message': 'No previous session found'}

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore file reads
            for path, info in data.get('file_reads', {}).items():
                self.working_memory['file_reads'][path] = {
                    'content': info['content'],
                    'timestamp': datetime.fromisoformat(info['timestamp']),
                    'lines': info['lines']
                }

            # Restore search results
            for search in data.get('search_results', []):
                self.working_memory['search_results'].append({
                    'query': search['query'],
                    'results': search['results'],
                    'timestamp': datetime.fromisoformat(search['timestamp'])
                })

            # Restore git operations
            for op in data.get('git_operations', []):
                self.working_memory['git_operations'].append({
                    'operation': op['operation'],
                    'output': op['output'],
                    'timestamp': datetime.fromisoformat(op['timestamp'])
                })

            # Restore discoveries
            for disc in data.get('discoveries', []):
                self.working_memory['discoveries'].append({
                    'finding': disc['finding'],
                    'location': disc['location'],
                    'timestamp': datetime.fromisoformat(disc['timestamp'])
                })

            # Restore task history
            self.task_history = data.get('task_history', [])

            # Get conversation history (will be returned to caller)
            conversation_history = data.get('conversation_history', [])

            return {
                'status': 'loaded',
                'saved_at': data.get('saved_at', 'unknown'),
                'files_restored': len(self.working_memory['file_reads']),
                'searches_restored': len(self.working_memory['search_results']),
                'git_ops_restored': len(self.working_memory['git_operations']),
                'discoveries_restored': len(self.working_memory['discoveries']),
                'tasks_restored': len(self.task_history),
                'conversation_history': conversation_history,
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def clear_session(self):
        """Delete saved session file."""
        session_file = self.context.project_path / ".llm_team_session.json"
        if session_file.exists():
            session_file.unlink()

    @property
    def providers(self) -> ProviderRegistry:
        """Access the provider registry."""
        return self.registry

    def status(self) -> dict:
        """
        Get current status of all providers.

        Returns:
            Dict with provider availability and limits
        """
        return {
            'available_providers': self.registry.list_available(),
            'all_providers': self.registry.list_all(),
            'provider_details': self.registry.get_provider_info(),
            'orchestrator_brain': self._brain_name,
            'tasks_executed': len(self.task_history),
            'session_start': self.created_at.isoformat(),
        }

    @property
    def brain(self):
        """Access the orchestrator's reasoning brain provider name."""
        if not self._brain_name:
            raise RuntimeError("No orchestrator brain configured. No providers available?")
        return self._brain_name

    @brain.setter
    def brain(self, provider_name: str):
        """Set the orchestrator's reasoning brain."""
        available = self.registry.list_available()
        if provider_name not in available:
            raise ValueError(f"Provider '{provider_name}' not available. Available: {available}")
        self._brain = self.registry.get(provider_name)
        self._brain_name = provider_name

    @property
    def brain_provider(self):
        """Access the actual brain provider object."""
        if not self._brain:
            raise RuntimeError("No orchestrator brain configured. No providers available?")
        return self._brain

    def plan(
        self,
        task: str,
        context: Optional[str] = None,
        max_steps: int = 10
    ) -> list[dict]:
        """
        Use the orchestrator brain to break down a complex task into steps.

        Args:
            task: The complex task to plan
            context: Optional context about the codebase/project
            max_steps: Maximum number of steps to generate

        Returns:
            List of step dicts with 'step', 'description', 'provider' keys

        Example:
            steps = orch.plan("Implement user authentication with JWT")
            for step in steps:
                result = orch.delegate(step['provider'], step['description'])
        """
        system_prompt = f"""You are a task planning assistant. Break down the given task into concrete, actionable steps.

For each step, specify:
1. A brief step name
2. A detailed description of what to do
3. Which provider type to use: 'fast' (simple tasks), 'quality' (complex reasoning), or 'high_volume' (many similar tasks)

Respond in this exact JSON format:
[
  {{"step": "step_name", "description": "what to do", "provider_type": "fast|quality|high_volume"}}
]

Maximum {max_steps} steps. Be specific and actionable."""

        user_prompt = task
        if context:
            user_prompt = f"Context:\n{context}\n\nTask:\n{task}"

        response = self.brain_provider.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            max_tokens=2000,
            temperature=0.3  # Lower temp for structured output
        )

        # Track this as an orchestration task
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'planning',
        })

        # Parse the response
        try:
            import json
            # Extract JSON from response (handle markdown code blocks)
            content = response.content.strip()
            if content.startswith('```'):
                # Remove markdown code block
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
            steps = json.loads(content)
            # Validate return type - must be list of dicts
            if not isinstance(steps, list):
                steps = [steps]
            # Ensure each item is a dict
            validated_steps = []
            for step in steps:
                if isinstance(step, dict):
                    validated_steps.append(step)
                else:
                    validated_steps.append({
                        'step': 'execute_task',
                        'description': str(step),
                        'provider_type': 'quality'
                    })
            return validated_steps
        except json.JSONDecodeError:
            # If parsing fails, return raw response as single step
            return [{
                'step': 'execute_task',
                'description': response.content,
                'provider_type': 'quality'
            }]

    def reason(
        self,
        question: str,
        context: Optional[str] = None,
        evidence: Optional[list[str]] = None
    ) -> dict:
        """
        Use the orchestrator brain for complex reasoning.

        Args:
            question: The question or problem to reason about
            context: Optional context information
            evidence: Optional list of evidence/facts to consider

        Returns:
            Dict with 'question', 'analysis', 'conclusion', 'confidence' keys

        Example:
            answer = orch.reason(
                "Should we use JWT or session-based auth?",
                context="Building a REST API for mobile app",
                evidence=["App needs offline support", "Multiple devices per user"]
            )
        """
        system_prompt = """You are a reasoning assistant. Analyze the question carefully, consider all evidence, and provide a well-reasoned response.

You MUST respond in this exact JSON format:
{
  "question": "the question being analyzed",
  "analysis": "detailed analysis of the considerations and factors",
  "conclusion": "your final recommendation or answer",
  "confidence": "high|medium|low"
}

Be thorough but concise. Do not repeat yourself. Provide unique insights in each section."""

        user_prompt = question
        if context:
            user_prompt = f"Context: {context}\n\nQuestion: {question}"
        if evidence:
            evidence_str = "\n".join(f"- {e}" for e in evidence)
            user_prompt += f"\n\nEvidence to consider:\n{evidence_str}"

        response = self.brain_provider.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            max_tokens=1500,
            temperature=0.3  # Lower temperature for structured output
        )

        # Track
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'reasoning',
        })

        # Parse JSON response
        try:
            import json
            content = response.content.strip()
            # Handle markdown code blocks
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
            result = json.loads(content)
            # Ensure result is a dict before calling .get()
            if not isinstance(result, dict):
                raise ValueError("Expected JSON object, got: " + type(result).__name__)
            # Ensure all expected keys exist
            return {
                'question': result.get('question', question),
                'analysis': result.get('analysis', ''),
                'conclusion': result.get('conclusion', ''),
                'confidence': result.get('confidence', 'unknown')
            }
        except (json.JSONDecodeError, KeyError):
            # Fallback: return raw content as analysis
            return {
                'question': question,
                'analysis': response.content,
                'conclusion': 'See analysis above',
                'confidence': 'unknown'
            }

    def synthesize(
        self,
        results: list[LLMResponse],
        synthesis_prompt: str = "Synthesize these results into a coherent summary:"
    ) -> str:
        """
        Use the brain to synthesize multiple agent results.

        Args:
            results: List of LLMResponse objects from various agents
            synthesis_prompt: Prompt for how to synthesize

        Returns:
            Synthesized summary
        """
        # Build context from results
        results_text = []
        for i, result in enumerate(results, 1):
            results_text.append(f"Result {i} (from {result.provider}/{result.model}):\n{result.content}")

        combined = "\n\n---\n\n".join(results_text)

        response = self.brain_provider.chat(
            messages=[
                {'role': 'system', 'content': 'You are a synthesis assistant. Combine multiple perspectives into a coherent whole.'},
                {'role': 'user', 'content': f"{synthesis_prompt}\n\n{combined}"}
            ],
            max_tokens=2000,
            temperature=0.4
        )

        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'synthesis',
        })

        return response.content

    def delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task to a specific provider.

        Args:
            provider_name: Name of provider ('groq', 'cohere', etc.)
            prompt: The user prompt/task
            model: Specific model to use (optional)
            system_prompt: System prompt for context (optional)
            max_tokens: Max response tokens
            temperature: Sampling temperature
            use_context: Override context_aware setting for this call
            use_cache: Override caching_enabled setting for this call
            intent_classification: Optional intent classification result for semantic caching
                                   Dict with keys: 'intent', 'entities', 'keywords'
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with result

        Example:
            # Simple delegation
            result = orch.delegate('groq', 'What is 2+2?')

            # With system prompt
            result = orch.delegate(
                'groq',
                'Review this code for bugs',
                system_prompt='You are a code reviewer. Be concise.'
            )

            # With context augmentation
            result = orch.delegate('groq', 'Fix the auth bug', use_context=True)

            # Without caching (for non-deterministic tasks)
            result = orch.delegate('groq', 'Generate random story', use_cache=False)

            # With intent-based caching
            from intent_classifier import IntentClassifier
            classifier = IntentClassifier()
            result = classifier.classify('how does caching work?')
            response = orch.delegate(
                'groq',
                'how does caching work?',
                intent_classification={
                    'intent': result.primary_intent.intent.value,
                    'entities': result.entities,
                    'keywords': result.keywords
                }
            )
        """
        provider = self.registry.get(provider_name)

        # Determine if we should use context
        should_use_context = use_context if use_context is not None else self.context_aware

        # Augment prompt with context if enabled and context is available
        final_prompt = prompt
        if should_use_context and self.context.is_explored():
            final_prompt = self.context.augment_prompt(prompt)

        # Add working memory context (session-scoped learnings)
        if should_use_context:
            working_memory_context = self.get_working_memory_context()
            if working_memory_context:
                final_prompt = working_memory_context + "\n\n" + final_prompt

        # Determine if we should use cache
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Check cache first (if enabled)
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            # Try exact match first (with normalization)
            cached_response = self.cache.get(
                provider_name,
                final_prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # If no exact match and intent classification provided, try intent cache
            if not cached_response and intent_classification:
                cached_response = self.cache.get_by_intent(
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', []),
                    provider_name,
                    model
                )
                if cached_response:
                    intent_cache_hit = True

        if cached_response:
            # Track cached hit
            self.task_history.append({
                'timestamp': datetime.now().isoformat(),
                'provider': provider_name,
                'model': cached_response.model,
                'tokens_used': cached_response.tokens_used,
                'latency_ms': 0.0,
                'context_augmented': should_use_context and self.context.is_explored(),
                'cached': True,
                'intent_cache_hit': intent_cache_hit,
            })
            return cached_response

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': final_prompt})

        # Execute
        response = provider.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        # Store in cache (if enabled)
        if should_use_cache:
            # Store in exact match cache (with normalization)
            self.cache.put(
                response,
                final_prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Also store in intent cache if classification provided
            if intent_classification:
                self.cache.put_by_intent(
                    response,
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', [])
                )

        # Track in rate limit tracker (persistent)
        self.rate_tracker.record_request(
            provider=provider_name,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            success=True
        )

        # Check for approaching limits and warn
        provider_limits = provider.get_limits()
        warnings = self.rate_tracker.is_limit_approaching(provider_name, response.model, provider_limits)
        if warnings.get('message'):
            # Store warning in response metadata
            response.metadata['rate_limit_warning'] = warnings['message']

        # Track
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': provider_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'context_augmented': should_use_context and self.context.is_explored(),
            'cached': False,
        })

        return response

    def delegate_with_intent(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task with automatic intent classification for semantic caching.

        This method automatically classifies the user prompt's intent and uses it
        for both exact match and intent-based caching. This increases cache hit rates
        for semantically similar queries.

        Args:
            provider_name: Name of provider ('groq', 'cohere', etc.)
            prompt: The user prompt/task
            model: Specific model to use (optional)
            system_prompt: System prompt for context (optional)
            max_tokens: Max response tokens
            temperature: Sampling temperature
            use_context: Override context_aware setting for this call
            use_cache: Override caching_enabled setting for this call
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with result

        Example:
            # Automatically classifies intent for better caching
            result = orch.delegate_with_intent('groq', 'how does the cache work?')
            # Later, this similar query may hit intent cache
            result = orch.delegate_with_intent('groq', 'explain how caching works')
        """
        from intent_classifier import IntentClassifier

        # Classify the prompt's intent
        classifier = IntentClassifier()
        classification_result = classifier.classify(prompt)

        # Build intent classification dict for caching
        intent_classification = {
            'intent': classification_result.primary_intent.intent.value,
            'entities': classification_result.entities,
            'keywords': classification_result.keywords
        }

        # Delegate with intent classification
        return self.delegate(
            provider_name=provider_name,
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=use_cache,
            intent_classification=intent_classification,
            **kwargs
        )

    def delegate_smart(
        self,
        prompt: str,
        task_type: str = 'general',
        **kwargs
    ) -> LLMResponse:
        """
        Automatically select best provider for task type.

        Args:
            prompt: The task/prompt
            task_type: Type of task
                - 'fast': Quick response needed (uses Cerebras > Groq)
                - 'quality': Best quality needed (uses Cerebras 70b > Groq 70b)
                - 'reasoning': Complex reasoning (use orchestrator brain)
                - 'high_volume': Many requests expected (uses Cerebras > Groq)
                - 'embed': Embedding task (uses Cohere - expensive!)
                - 'general': General task (uses Cerebras > Groq)
            **kwargs: Additional parameters

        Returns:
            LLMResponse with result
        """
        available = self.registry.list_available()

        if not available:
            raise RuntimeError("No providers available!")

        # Routing logic - Cerebras is now primary
        if task_type in ['fast', 'high_volume', 'general']:
            # Prefer Cerebras (14,400 RPD), then Groq (7,000 RPD)
            if 'cerebras' in available:
                provider = self.registry.get('cerebras')
                model = provider.get_model_for_task(task_type)
                return self.delegate('cerebras', prompt, model=model, **kwargs)
            elif 'groq' in available:
                provider = self.registry.get('groq')
                model = provider.get_model_for_task(task_type)
                return self.delegate('groq', prompt, model=model, **kwargs)

        elif task_type == 'reasoning':
            # Use the orchestrator brain for reasoning
            reasoning_result = self.reason(prompt)
            # Convert dict to string for LLMResponse content
            if isinstance(reasoning_result, dict):
                content = f"Analysis: {reasoning_result.get('analysis', '')}\n\nConclusion: {reasoning_result.get('conclusion', '')}"
            else:
                content = str(reasoning_result)
            return LLMResponse(
                content=content,
                model=self.brain_provider.default_model,
                provider=self._brain_name,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                raw_response=reasoning_result,
                metadata={'task_type': 'reasoning', 'via': 'orchestrator_brain'},
                timestamp=datetime.now()
            )

        elif task_type == 'quality':
            # Use best available large model
            if 'cerebras' in available:
                return self.delegate(
                    'cerebras',
                    prompt,
                    model='llama-3.3-70b',
                    **kwargs
                )
            elif 'groq' in available:
                return self.delegate(
                    'groq',
                    prompt,
                    model='llama-3.3-70b-versatile',
                    **kwargs
                )

        elif task_type == 'embed' and 'cohere' in available:
            print("WARNING: Using Cohere. This counts toward 1,000/month limit!")
            return self.delegate('cohere', prompt, **kwargs)

        # Fallback: use first available provider
        provider_name = available[0]
        return self.delegate(provider_name, prompt, **kwargs)

    def batch_delegate(
        self,
        tasks: list[dict],
        provider_name: str = 'groq'
    ) -> list[LLMResponse]:
        """
        Process multiple tasks with same provider.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt'
            provider_name: Provider to use for all tasks

        Returns:
            List of LLMResponse objects

        Example:
            tasks = [
                {'prompt': 'Summarize: ...'},
                {'prompt': 'Translate: ...'},
                {'prompt': 'Classify: ...'},
            ]
            results = orch.batch_delegate(tasks)
        """
        results = []
        for task in tasks:
            result = self.delegate(
                provider_name,
                task['prompt'],
                system_prompt=task.get('system_prompt'),
                **task.get('kwargs', {})
            )
            results.append(result)
        return results

    def get_usage_report(self) -> dict:
        """
        Get usage statistics for current session.

        Returns:
            Dict with usage metrics by provider
        """
        if not self.task_history:
            return {
                'message': 'No tasks executed yet',
                'cache_stats': self.cache.get_stats()
            }

        # Aggregate by provider
        by_provider = {}
        cached_hits = 0
        for task in self.task_history:
            provider = task['provider']
            if provider not in by_provider:
                by_provider[provider] = {
                    'count': 0,
                    'total_tokens': 0,
                    'total_latency_ms': 0,
                    'cached_hits': 0,
                }
            by_provider[provider]['count'] += 1
            by_provider[provider]['total_tokens'] += task['tokens_used']
            by_provider[provider]['total_latency_ms'] += task['latency_ms']

            # Count cached hits
            if task.get('cached', False):
                by_provider[provider]['cached_hits'] += 1
                cached_hits += 1

        # Calculate averages
        for provider, stats in by_provider.items():
            stats['avg_tokens'] = stats['total_tokens'] / stats['count']
            stats['avg_latency_ms'] = stats['total_latency_ms'] / stats['count']

        return {
            'total_tasks': len(self.task_history),
            'cached_hits': cached_hits,
            'api_calls': len(self.task_history) - cached_hits,
            'by_provider': by_provider,
            'session_duration': str(datetime.now() - self.created_at),
            'cache_stats': self.cache.get_stats(),
        }

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.get_stats()

    def clear_cache(self):
        """Clear the response cache."""
        self.cache.clear()

    def toggle_cache(self) -> bool:
        """Toggle caching on/off. Returns new state."""
        self.caching_enabled = not self.caching_enabled
        return self.caching_enabled

    def get_rate_limit_status(self) -> dict:
        """
        Get current rate limit usage for all providers.

        Returns:
            Dict with usage statistics and remaining quotas
        """
        status = self.rate_tracker.get_all_usage_summary()

        # Add remaining quota info for each provider
        for provider_name in status.get('providers', {}):
            try:
                provider = self.registry.get(provider_name)
                limits = provider.get_limits()

                # Get remaining for default model
                remaining = self.rate_tracker.get_remaining_quota(
                    provider_name,
                    provider.default_model,
                    limits
                )
                status['providers'][provider_name]['limits'] = {
                    'requests_per_day': limits.requests_per_day,
                    'requests_per_month': limits.requests_per_month,
                    'tokens_per_day': limits.tokens_per_day,
                    'tokens_per_minute': limits.tokens_per_minute,
                }
                status['providers'][provider_name]['remaining'] = remaining
            except Exception:
                pass  # Provider might not be available

        return status

    def get_remaining_quota(self, provider_name: str, model: Optional[str] = None) -> dict:
        """
        Get remaining quota for a specific provider.

        Args:
            provider_name: Name of provider
            model: Specific model (optional, uses default if not specified)

        Returns:
            Dict with remaining requests and tokens
        """
        provider = self.registry.get(provider_name)
        limits = provider.get_limits()

        if model is None:
            model = provider.default_model

        return self.rate_tracker.get_remaining_quota(provider_name, model, limits)

    def check_rate_limit_warnings(self) -> list[str]:
        """
        Check for any approaching rate limits across all providers.

        Returns:
            List of warning messages
        """
        warnings = []

        for provider_name in self.registry.list_available():
            try:
                provider = self.registry.get(provider_name)
                limits = provider.get_limits()

                # Check each model that has been used
                usage = self.rate_tracker.get_usage(provider_name)
                for model in usage.keys():
                    warning_info = self.rate_tracker.is_limit_approaching(provider_name, model, limits)
                    if warning_info.get('message'):
                        warnings.append(warning_info['message'])
            except Exception:
                pass

        return warnings

    def reset_rate_tracking(self, provider_name: Optional[str] = None):
        """
        Reset rate tracking data.

        Args:
            provider_name: Specific provider to reset (optional, resets all if not specified)
        """
        if provider_name:
            self.rate_tracker.reset_provider(provider_name)
        else:
            self.rate_tracker.clear()

    def recommend_provider(self, requirements: dict) -> str:
        """
        Recommend best provider based on requirements.

        Args:
            requirements: Dict with keys like:
                - 'speed': 'fast' | 'moderate' | 'slow'
                - 'quality': 'moderate' | 'good' | 'excellent'
                - 'budget_sensitive': bool
                - 'task_count': int (how many similar tasks)

        Returns:
            Recommended provider name
        """
        available = self.registry.list_available()

        if not available:
            raise RuntimeError("No providers available!")

        # Budget sensitive -> prefer Groq (more quota)
        if requirements.get('budget_sensitive', True):
            if 'groq' in available:
                return 'groq'

        # High volume -> Groq
        if requirements.get('task_count', 1) > 10:
            if 'groq' in available:
                return 'groq'

        # Speed priority -> Groq
        if requirements.get('speed') == 'fast':
            if 'groq' in available:
                return 'groq'

        # Quality priority and willing to use quota -> Cohere
        if requirements.get('quality') == 'excellent':
            if 'cohere' in available and not requirements.get('budget_sensitive', True):
                return 'cohere'

        # Default to Groq if available
        return available[0]


def create_orchestrator() -> AgentOrchestrator:
    """
    Factory function to create an orchestrator.

    Returns:
        Configured AgentOrchestrator instance
    """
    return AgentOrchestrator(auto_register=True)
