"""
Core AgentOrchestrator implementation.

Central coordinator for multi-provider LLM agent team using composition.
"""

from typing import Optional
from datetime import datetime
import asyncio
import time

try:
    from ..providers import ProviderRegistry, GroqProvider, CohereProvider, GeminiProvider, CerebrasProvider, GitHubModelsProvider, LLMResponse
    from ..context import CodebaseContext
    from ..utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError
except ImportError:
    from providers import ProviderRegistry, GroqProvider, CohereProvider, GeminiProvider, CerebrasProvider, GitHubModelsProvider, LLMResponse
    from context import CodebaseContext
    from utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError

from .cache import ResponseCache
from .rate_limiter import RateLimitTracker
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .output import OutputInterface, ConsoleOutput


class AgentOrchestrator:
    """
    Central coordinator for multi-provider LLM agent team.

    Usage with Claude Code as reasoning layer:
        orch = AgentOrchestrator()
        result = orch.delegate('groq', 'Summarize this text: ...')
        embeddings = orch.providers.get('cohere').embed(['text1', 'text2'])
    """

    def __init__(
        self,
        auto_register: bool = True,
        orchestrator_provider: Optional[str] = None,
        project_path: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        enable_cache: bool = True,
        cache_ttl_hours: int = 24,
        verbose_selection: bool = False,
        show_provider_status: bool = False,
        output: Optional[OutputInterface] = None
    ):
        """
        Initialize orchestrator.

        Args:
            auto_register: Automatically register available providers
            orchestrator_provider: Provider to use as the "brain" for planning/reasoning
            project_path: Path to project for context awareness
            auto_explore: Automatically explore codebase on init
            context_aware: Enable context-augmented prompts
            enable_cache: Enable response caching
            cache_ttl_hours: Time-to-live for cache entries in hours
            verbose_selection: Show detailed provider selection logic
            show_provider_status: Display provider status summary on startup
            output: Output interface for messages (default: ConsoleOutput)
        """
        # Core components
        self.output = output or ConsoleOutput()
        self.registry = ProviderRegistry()
        self.task_history: list[dict] = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = orchestrator_provider
        self.context_aware = context_aware
        self.caching_enabled = enable_cache
        self.verbose_selection = verbose_selection
        self._show_provider_status = show_provider_status

        # Background task management (for fire-and-forget operations)
        self._background_tasks: set = set()
        self._background_errors: list = []

        # Initialize codebase context
        self.context = CodebaseContext(project_path)

        # Initialize composed components
        self.cache = ResponseCache(
            cache_file=str(self.context.project_path / ".llm_response_cache.json"),
            default_ttl_hours=cache_ttl_hours
        )
        self.rate_tracker = RateLimitTracker(
            tracker_file=str(self.context.project_path / ".llm_rate_limits.json")
        )
        self.working_memory = WorkingMemory()
        self.session_manager = SessionManager(self.context.project_path)
        self.provider_selector = ProviderSelector(self.registry, verbose=verbose_selection, output=self.output)

        # Register providers and set up brain
        if auto_register:
            self._auto_register_providers()
            self._setup_brain(orchestrator_provider)
            if show_provider_status:
                self.print_provider_status()

        # Initialize task executor after brain is set up
        self.task_executor = TaskExecutor(
            get_brain_provider=lambda: self._brain,
            get_brain_name=lambda: self._brain_name,
            record_task=lambda task: self.task_history.append(task)
        )

        # Auto-explore if requested
        if auto_explore and self._brain:
            self._auto_explore()

    def _auto_register_providers(self):
        """Attempt to register all known providers."""
        # Try GitHub Models (RECOMMENDED BRAIN - GPT-4o with 10K RPD)
        try:
            self.registry.register(GitHubModelsProvider())
            self.output.success("GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)")
        except Exception as e:
            self.output.error(f"GitHub Models provider unavailable: {e}")

        # Try Cerebras (primary workhorse - highest quota)
        try:
            self.registry.register(CerebrasProvider())
            self.output.success("Cerebras provider registered (14,400 RPD)")
        except Exception as e:
            self.output.error(f"Cerebras provider unavailable: {e}")

        # Try Groq (secondary)
        try:
            self.registry.register(GroqProvider())
            self.output.success("Groq provider registered (7,000 RPD)")
        except Exception as e:
            self.output.error(f"Groq provider unavailable: {e}")

        # Try Gemini (with auto-fallback)
        try:
            self.registry.register(GeminiProvider())
            self.output.success("Gemini provider registered (auto-fallback enabled)")
        except Exception as e:
            self.output.error(f"Gemini provider unavailable: {e}")

        # Try Cohere (limited - embeddings only)
        try:
            self.registry.register(CohereProvider())
            self.output.success("Cohere provider registered (1,000/month - use sparingly)")
        except Exception as e:
            self.output.error(f"Cohere provider unavailable: {e}")

    def _setup_brain(self, preferred_provider: Optional[str] = None):
        """Set up the orchestrator's reasoning brain."""
        try:
            self._brain_name, self._brain = self.provider_selector.setup_brain(preferred_provider)
            self.output.info(f"[BRAIN] Using {self._brain_name} as orchestrator brain")
        except RuntimeError as e:
            self.output.warn(str(e))

    def _auto_explore(self):
        """Automatically explore the codebase if not already explored."""
        if self.context.is_explored():
            self.output.info(f"[CONTEXT] Loaded cached context for {self.context.project_path.name}")
            return

        self.output.info(f"[CONTEXT] Exploring codebase: {self.context.project_path}")
        result = self.context.explore()

        if result['status'] == 'explored':
            self.output.info(f"[CONTEXT] Found {result['total_files']} files")
            self.context.generate_summary(self.task_executor.generate_context_summary)
            self.output.info("[CONTEXT] Generated project summary")

    # Provider Management

    @property
    def providers(self) -> ProviderRegistry:
        """Access the provider registry."""
        return self.registry

    @property
    def brain(self):
        """Access the orchestrator's reasoning brain provider name.

        Returns None if no brain is configured (e.g., no providers available).
        """
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

    def status(self) -> dict:
        """Get current status of all providers."""
        return {
            'available_providers': self.registry.list_available(),
            'all_providers': self.registry.list_all(),
            'provider_details': self.registry.get_provider_info(),
            'orchestrator_brain': self._brain_name,
            'tasks_executed': len(self.task_history),
            'session_start': self.created_at.isoformat(),
        }

    def print_provider_status(self):
        """Print comprehensive provider status summary."""
        self.output.info("\n" + "=" * 60)
        self.output.info("PROVIDER CONFIGURATION SUMMARY")
        self.output.info("=" * 60)

        available = self.registry.list_available()
        all_known = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']

        self.output.info("\nProvider Status:")
        for provider_name in all_known:
            if provider_name in available:
                reason = self.provider_selector._get_brain_selection_reason(provider_name)
                status_str = f"  [OK] {provider_name:<15} - {reason}"
            else:
                status_str = f"  [--] {provider_name:<15} - NOT AVAILABLE (missing API key or package)"
            self.output.info(status_str)

        self.output.info(f"\nSelected Brain: {self._brain_name}")
        if self._brain_name:
            reason = self.provider_selector._get_brain_selection_reason(self._brain_name)
            self.output.info(f"Selection Reason: {reason}")

        self.output.info("\nSelection Priority: cerebras > groq > gemini")
        self.output.info("Use --brain <provider> to override auto-selection")

        if self.verbose_selection and self.provider_selector.get_selection_log():
            self.output.info("\nSelection Log:")
            for entry in self.provider_selector.get_selection_log():
                self.output.info(f"  {entry}")

        self.output.info("=" * 60 + "\n")

    def get_provider_selection_info(self) -> dict:
        """Get detailed provider selection information."""
        available = self.registry.list_available()
        all_known = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']

        provider_info = {}
        for provider_name in all_known:
            provider_info[provider_name] = {
                'available': provider_name in available,
                'reason': self.provider_selector._get_brain_selection_reason(provider_name) if provider_name in available else 'not available'
            }

        return {
            'available_providers': available,
            'all_known_providers': all_known,
            'selected_brain': self._brain_name,
            'selection_priority': ['cerebras', 'groq', 'gemini'],
            'provider_details': provider_info,
            'selection_log': self.provider_selector.get_selection_log()
        }

    # Context Management

    def explore_project(self, force: bool = False) -> dict:
        """Manually trigger project exploration."""
        if force:
            self.context.clear_cache()

        result = self.context.explore(force=force)

        if result['status'] == 'explored' or force:
            self.context.generate_summary(self.task_executor.generate_context_summary)

        return result

    def get_context_status(self) -> dict:
        """Get current codebase context status."""
        return self.context.get_status()

    # Working Memory (delegates to WorkingMemory)

    def remember_file_read(self, path: str, content: str, lines: int = 0):
        """Store a file read in working memory."""
        self.working_memory.remember_file_read(path, content, lines)

    def remember_search(self, query: str, results: list):
        """Store a search result in working memory."""
        self.working_memory.remember_search(query, results)

    def remember_git_operation(self, operation: str, output: str):
        """Store a git operation result in working memory."""
        self.working_memory.remember_git_operation(operation, output)

    def add_discovery(self, finding: str, location: str = ""):
        """Add a discovery/learning to working memory."""
        self.working_memory.add_discovery(finding, location)

    def get_working_memory_summary(self) -> dict:
        """Get a summary of current working memory state."""
        return self.working_memory.get_summary()

    def get_working_memory_context(self) -> str:
        """Build context string from working memory for LLM augmentation."""
        return self.working_memory.get_context_string()

    def clear_working_memory(self):
        """Clear all working memory."""
        self.working_memory.clear()

    # Session Management (delegates to SessionManager)

    def save_session(self, conversation_history: list = None) -> str:
        """Save current session to disk."""
        return self.session_manager.save_session(
            self.working_memory,
            self.task_history,
            self.created_at,
            conversation_history
        )

    def load_session(self) -> dict:
        """Load previous session from disk."""
        result = self.session_manager.load_session()

        if result['status'] == 'loaded':
            # Restore working memory
            self.working_memory = result['working_memory']
            # Restore task history
            self.task_history = result['task_history']

            # Return relevant info (remove internal working_memory object)
            return {
                'status': 'loaded',
                'saved_at': result['saved_at'],
                'files_restored': result['files_restored'],
                'searches_restored': result['searches_restored'],
                'git_ops_restored': result['git_ops_restored'],
                'discoveries_restored': result['discoveries_restored'],
                'tasks_restored': result['tasks_restored'],
                'conversation_history': result['conversation_history'],
            }

        return result

    def clear_session(self):
        """Delete saved session file."""
        self.session_manager.clear_session()

    # Task Execution (delegates to TaskExecutor)

    def plan(self, task: str, context: Optional[str] = None, max_steps: int = 10) -> list[dict]:
        """Break down a complex task into steps."""
        return self.task_executor.plan(task, context, max_steps)

    def reason(self, question: str, context: Optional[str] = None, evidence: Optional[list[str]] = None) -> dict:
        """Use the orchestrator brain for complex reasoning."""
        return self.task_executor.reason(question, context, evidence)

    def synthesize(self, results: list[LLMResponse], synthesis_prompt: str = "Synthesize these results into a coherent summary:") -> str:
        """Synthesize multiple agent results."""
        return self.task_executor.synthesize(results, synthesis_prompt)

    # Provider Selection

    def get_recommended_provider(self, task_type: str = 'general') -> Optional[str]:
        """
        Get recommended provider based on task type and current rate limit status.

        Args:
            task_type: Type of task ('planning', 'execution', 'quick', 'general')

        Returns:
            Provider name or None if no providers available
        """
        available = self.registry.list_available()
        if not available:
            return None

        # Define provider preferences by task type
        # Cerebras llama-3.3-70b preferred for planning (best quality/speed balance)
        # Groq llama-4-scout-17b-16e-instruct as secondary option
        task_preferences = {
            'planning': ['cerebras', 'groq', 'gemini'],  # Cerebras 70b for quality+speed
            'execution': ['cerebras', 'groq', 'gemini'],  # Speed
            'quick': ['cerebras', 'groq'],  # Fast responses
            'general': ['cerebras', 'groq', 'gemini']  # Balanced
        }

        preferences = task_preferences.get(task_type, task_preferences['general'])

        # Filter out rate-limited providers
        for provider_name in preferences:
            if provider_name not in available:
                continue

            # Check rate limit status
            if self.is_rate_limited(provider_name):
                continue

            return provider_name

        # Fallback: return first available provider even if rate-limited
        return available[0] if available else None

    def is_rate_limited(self, provider_name: str) -> bool:
        """
        Check if a provider is currently rate limited.

        Args:
            provider_name: Name of provider to check

        Returns:
            True if provider is rate limited, False otherwise
        """
        provider = self.registry.get(provider_name)
        if not provider:
            return False

        limits = provider.get_limits()
        if not limits:
            return False

        # Get default model for this provider
        model = getattr(provider, 'default_model', 'default')

        # Check remaining quota
        remaining = self.rate_tracker.get_remaining_quota(provider_name, model, limits)

        # Consider rate limited if no requests remaining today or this month
        if remaining.get('requests_remaining_today') == 0:
            return True
        if remaining.get('requests_remaining_month') == 0:
            return True

        return False

    # Delegation

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        task_type: str = 'general',
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task to a specific provider with automatic fallback on rate limits.

        Args:
            provider_name: Initial provider to try (None for auto-selection)
            prompt: The prompt to send
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            intent_classification: Intent data for semantic caching
            auto_fallback: Automatically try other providers on rate limit (default True)
            max_retries: Maximum retry attempts per provider (default 3)
            task_type: Type of task for auto provider selection ('planning', 'execution', 'general')
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            Exception: Other non-rate-limit errors
        """
        # Auto-select provider if not specified
        if provider_name is None:
            provider_name = self.get_recommended_provider(task_type)
            if provider_name is None:
                raise Exception("No providers available")

        # Determine settings
        should_use_context = use_context if use_context is not None else self.context_aware
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Augment prompt with context if enabled
        final_prompt = prompt
        if should_use_context and self.context.is_explored():
            final_prompt = self.context.augment_prompt(prompt)

        # Add working memory context
        if should_use_context:
            working_memory_context = self.get_working_memory_context()
            if working_memory_context:
                final_prompt = working_memory_context + "\n\n" + final_prompt

        # Check cache first (cache hits don't need fallback)
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self.cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
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

        # Track which providers we've tried
        attempted_providers = []
        current_provider_name = provider_name
        current_model = model

        while True:
            provider = self.registry.get(current_provider_name)

            # Proactive limit check - warn if approaching limits
            try:
                provider_limits = provider.get_limits()
                remaining = self.rate_tracker.get_remaining_quota(
                    current_provider_name, current_model or provider.default_model, provider_limits
                )

                # If we're very close to limit (less than 5% remaining), try fallback first
                if remaining.get('requests_today_remaining', 100) <= 0:
                    self.output.warn(f"{current_provider_name} has exhausted daily quota, trying fallback...")
                    raise RateLimitError(current_provider_name, "Daily quota exhausted", "requests")
            except RateLimitError:
                raise  # Re-raise rate limit errors
            except Exception:
                pass  # Ignore other errors in limit checking

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = provider.chat(
                        messages=messages,
                        model=current_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )

                    # Success! Store in cache
                    if should_use_cache:
                        self.cache.put(response, final_prompt, current_model, system_prompt, max_tokens, temperature)
                        if intent_classification:
                            self.cache.put_by_intent(
                                response,
                                intent_classification.get('intent', ''),
                                intent_classification.get('entities', {}),
                                intent_classification.get('keywords', [])
                            )

                    # Track rate limits
                    self.rate_tracker.record_request(
                        provider=current_provider_name,
                        model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        success=True
                    )

                    # Check for approaching limits
                    warnings = self.rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != provider_name:
                        response.metadata['fallback_from'] = provider_name
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Track task
                    self.task_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'context_augmented': should_use_context and self.context.is_explored(),
                        'cached': False,
                        'fallback': current_provider_name != provider_name,
                        'attempts': attempt + 1,
                    })

                    return response

                except Exception as e:
                    last_error = e

                    # Check if it's a rate limit error
                    if is_rate_limit_error(e):
                        # Record the failed request
                        self.rate_tracker.record_request(
                            provider=current_provider_name,
                            model=current_model or provider.default_model,
                            input_tokens=0,
                            output_tokens=0,
                            success=False,
                            error_message=str(e)
                        )

                        if attempt < max_retries - 1:
                            # Exponential backoff before retry
                            wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s
                            self.output.warn(f"Rate limit hit on {current_provider_name}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                        else:
                            # Max retries reached, will try fallback
                            self.output.warn(f"Rate limit persists on {current_provider_name} after {max_retries} attempts")
                            break
                    else:
                        # Not a rate limit error, re-raise immediately
                        raise

            # If we got here, we've exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            # Try fallback if enabled
            if not auto_fallback:
                raise last_error

            # Get next fallback provider
            fallback_provider = self.provider_selector.get_provider_for_fallback(exclude=attempted_providers)

            if fallback_provider is None:
                # No more providers available
                self.output.error(f"All providers rate limited. Attempted: {attempted_providers}")
                raise AllProvidersRateLimitedError(attempted_providers)

            self.output.info(f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}")
            current_provider_name = fallback_provider
            current_model = None  # Reset model for new provider

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
        """Delegate a task with automatic intent classification for semantic caching."""
        from intent_classifier import IntentClassifier

        classifier = IntentClassifier()
        classification_result = classifier.classify(prompt)

        intent_classification = {
            'intent': classification_result.primary_intent.intent.value,
            'entities': classification_result.entities,
            'keywords': classification_result.keywords
        }

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

    def delegate_smart(self, prompt: str, task_type: str = 'general', **kwargs) -> LLMResponse:
        """Automatically select best provider for task type."""
        if task_type == 'reasoning':
            reasoning_result = self.reason(prompt)
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

        provider_name, model = self.provider_selector.select_for_task(task_type)
        return self.delegate(provider_name, prompt, model=model, **kwargs)

    def batch_delegate(self, tasks: list[dict], provider_name: str = 'groq') -> list[LLMResponse]:
        """Process multiple tasks with same provider."""
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

    # Async Methods

    async def delegate_async(
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
        auto_fallback: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> LLMResponse:
        """
        Async version of delegate with automatic fallback on rate limits.

        Enables parallel execution of multiple LLM requests with recovery.

        Args:
            provider_name: Initial provider to try
            prompt: The prompt to send
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            intent_classification: Intent data for semantic caching
            auto_fallback: Automatically try other providers on rate limit (default True)
            max_retries: Maximum retry attempts per provider (default 3)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            Exception: Other non-rate-limit errors
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self.context_aware
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Augment prompt with context if enabled
        final_prompt = prompt
        if should_use_context and self.context.is_explored():
            final_prompt = self.context.augment_prompt(prompt)

        # Add working memory context
        if should_use_context:
            working_memory_context = self.get_working_memory_context()
            if working_memory_context:
                final_prompt = working_memory_context + "\n\n" + final_prompt

        # Check cache first (cache hits don't need fallback)
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self.cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
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
            self.task_history.append({
                'timestamp': datetime.now().isoformat(),
                'provider': provider_name,
                'model': cached_response.model,
                'tokens_used': cached_response.tokens_used,
                'latency_ms': 0.0,
                'context_augmented': should_use_context and self.context.is_explored(),
                'cached': True,
                'intent_cache_hit': intent_cache_hit,
                'async': True,
            })
            return cached_response

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': final_prompt})

        # Track which providers we've tried
        attempted_providers = []
        current_provider_name = provider_name
        current_model = model

        while True:
            provider = self.registry.get(current_provider_name)

            # Proactive limit check
            try:
                provider_limits = provider.get_limits()
                remaining = self.rate_tracker.get_remaining_quota(
                    current_provider_name, current_model or provider.default_model, provider_limits
                )

                if remaining.get('requests_today_remaining', 100) <= 0:
                    self.output.warn(f"{current_provider_name} has exhausted daily quota, trying fallback...")
                    raise RateLimitError(current_provider_name, "Daily quota exhausted", "requests")
            except RateLimitError:
                raise
            except Exception:
                pass

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = await provider.chat_async(
                        messages=messages,
                        model=current_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )

                    # Success! Store in cache (background)
                    if should_use_cache:
                        self._schedule_background_task(
                            self.cache.put_async(response, final_prompt, current_model, system_prompt, max_tokens, temperature)
                        )
                        if intent_classification:
                            self._schedule_background_task(
                                self.cache.put_by_intent_async(
                                    response,
                                    intent_classification.get('intent', ''),
                                    intent_classification.get('entities', {}),
                                    intent_classification.get('keywords', [])
                                )
                            )

                    # Track rate limits (background)
                    self._schedule_background_task(
                        self.rate_tracker.record_request_async(
                            provider=current_provider_name,
                            model=response.model,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            success=True
                        )
                    )

                    # Check for approaching limits
                    warnings = self.rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != provider_name:
                        response.metadata['fallback_from'] = provider_name
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Track task
                    self.task_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'context_augmented': should_use_context and self.context.is_explored(),
                        'cached': False,
                        'async': True,
                        'fallback': current_provider_name != provider_name,
                        'attempts': attempt + 1,
                    })

                    return response

                except Exception as e:
                    last_error = e

                    if is_rate_limit_error(e):
                        # Record the failed request (background)
                        self._schedule_background_task(
                            self.rate_tracker.record_request_async(
                                provider=current_provider_name,
                                model=current_model or provider.default_model,
                                input_tokens=0,
                                output_tokens=0,
                                success=False,
                                error_message=str(e)
                            )
                        )

                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * 0.5
                            self.output.warn(f"Rate limit hit on {current_provider_name}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(wait_time)
                        else:
                            self.output.warn(f"Rate limit persists on {current_provider_name} after {max_retries} attempts")
                            break
                    else:
                        raise

            # Exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            if not auto_fallback:
                raise last_error

            # Get next fallback provider
            fallback_provider = self.provider_selector.get_provider_for_fallback(exclude=attempted_providers)

            if fallback_provider is None:
                self.output.error(f"All providers rate limited. Attempted: {attempted_providers}")
                raise AllProvidersRateLimitedError(attempted_providers)

            self.output.info(f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}")
            current_provider_name = fallback_provider
            current_model = None

    async def batch_delegate_async(
        self,
        tasks: list[dict],
        provider_name: str = 'groq',
        max_concurrent: int = 5
    ) -> list[LLMResponse]:
        """
        Process multiple tasks in parallel using async.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            max_concurrent: Maximum number of concurrent requests (to respect rate limits)

        Returns:
            List of LLMResponse objects in the same order as input tasks

        Example:
            tasks = [
                {'prompt': 'Summarize this: ...'},
                {'prompt': 'Analyze this: ...'},
                {'prompt': 'Explain this: ...'}
            ]
            results = await orch.batch_delegate_async(tasks, 'cerebras', max_concurrent=3)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_task(task):
            async with semaphore:
                return await self.delegate_async(
                    provider_name,
                    task['prompt'],
                    system_prompt=task.get('system_prompt'),
                    **task.get('kwargs', {})
                )

        # Execute all tasks concurrently (limited by semaphore)
        results = await asyncio.gather(*[process_task(task) for task in tasks])
        return list(results)

    async def multi_provider_query_async(
        self,
        prompt: str,
        providers: list[str] = None,
        **kwargs
    ) -> dict[str, LLMResponse]:
        """
        Query multiple providers in parallel for the same prompt.

        Useful for getting different perspectives or comparing outputs.

        Args:
            prompt: The prompt to send to all providers
            providers: List of provider names (defaults to all available)
            **kwargs: Additional arguments passed to delegate_async

        Returns:
            Dict mapping provider name to LLMResponse
        """
        if providers is None:
            providers = self.registry.list_available()

        async def query_provider(provider_name):
            try:
                response = await self.delegate_async(provider_name, prompt, **kwargs)
                return provider_name, response
            except Exception as e:
                self.output.warn(f"{provider_name} failed: {e}")
                return provider_name, None

        results = await asyncio.gather(*[query_provider(p) for p in providers])
        return {name: response for name, response in results if response is not None}

    def run_async(self, coro):
        """
        Helper to run async code from sync context.

        Usage:
            results = orch.run_async(orch.batch_delegate_async(tasks))
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new task
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(coro)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop, create a new one
            return asyncio.run(coro)

    # Usage and Cache Statistics

    def get_usage_report(self) -> dict:
        """Get usage statistics for current session."""
        if not self.task_history:
            return {'message': 'No tasks executed yet', 'cache_stats': self.cache.get_stats()}

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

            if task.get('cached', False):
                by_provider[provider]['cached_hits'] += 1
                cached_hits += 1

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

    # Background Task Management

    def _schedule_background_task(self, coro):
        """
        Schedule a coroutine as a background task (fire-and-forget).

        The task will run without blocking the caller. Errors are captured
        but don't affect the main flow.

        Args:
            coro: Coroutine to execute in background
        """
        task = asyncio.create_task(coro)

        # Add to tracking set (prevents garbage collection)
        self._background_tasks.add(task)

        # Remove from set when done and capture any errors
        def on_done(t):
            self._background_tasks.discard(t)
            if t.exception():
                self._background_errors.append({
                    'timestamp': datetime.now().isoformat(),
                    'error': str(t.exception()),
                    'type': type(t.exception()).__name__
                })
                # Keep only last 50 errors
                self._background_errors = self._background_errors[-50:]

        task.add_done_callback(on_done)

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> dict:
        """
        Wait for all pending background tasks to complete.

        Useful for testing or graceful shutdown.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Dict with completion status
        """
        if not self._background_tasks:
            return {
                'status': 'no_pending',
                'completed': 0,
                'errors': len(self._background_errors)
            }

        pending_count = len(self._background_tasks)

        try:
            # Wait for all tasks with timeout
            done, pending = await asyncio.wait(
                self._background_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            return {
                'status': 'completed' if not pending else 'timeout',
                'completed': len(done),
                'pending': len(pending),
                'errors': len(self._background_errors)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'pending': pending_count
            }

    def get_background_task_status(self) -> dict:
        """
        Get status of background task processing.

        Returns:
            Dict with pending task count and recent errors
        """
        return {
            'pending_tasks': len(self._background_tasks),
            'recent_errors': self._background_errors[-10:],
            'total_errors': len(self._background_errors)
        }

    def clear_background_errors(self):
        """Clear the background error log."""
        self._background_errors.clear()

    # Rate Limit Management

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit usage for all providers."""
        status = self.rate_tracker.get_all_usage_summary()

        for provider_name in status.get('providers', {}):
            try:
                provider = self.registry.get(provider_name)
                limits = provider.get_limits()
                remaining = self.rate_tracker.get_remaining_quota(
                    provider_name, provider.default_model, limits
                )
                status['providers'][provider_name]['limits'] = {
                    'requests_per_day': limits.requests_per_day,
                    'requests_per_month': limits.requests_per_month,
                    'tokens_per_day': limits.tokens_per_day,
                    'tokens_per_minute': limits.tokens_per_minute,
                }
                status['providers'][provider_name]['remaining'] = remaining
            except Exception:
                pass

        return status

    def get_remaining_quota(self, provider_name: str, model: Optional[str] = None) -> dict:
        """Get remaining quota for a specific provider."""
        provider = self.registry.get(provider_name)
        limits = provider.get_limits()
        if model is None:
            model = provider.default_model
        return self.rate_tracker.get_remaining_quota(provider_name, model, limits)

    def check_rate_limit_warnings(self) -> list[str]:
        """Check for any approaching rate limits across all providers."""
        warnings = []
        for provider_name in self.registry.list_available():
            try:
                provider = self.registry.get(provider_name)
                limits = provider.get_limits()
                usage = self.rate_tracker.get_usage(provider_name)
                for model in usage.keys():
                    warning_info = self.rate_tracker.is_limit_approaching(provider_name, model, limits)
                    if warning_info.get('message'):
                        warnings.append(warning_info['message'])
            except Exception:
                pass
        return warnings

    def reset_rate_tracking(self, provider_name: Optional[str] = None):
        """Reset rate tracking data."""
        if provider_name:
            self.rate_tracker.reset_provider(provider_name)
        else:
            self.rate_tracker.clear()

    def recommend_provider(self, requirements: dict) -> str:
        """Recommend best provider based on requirements."""
        return self.provider_selector.recommend(requirements)


def create_orchestrator() -> AgentOrchestrator:
    """Factory function to create an orchestrator."""
    return AgentOrchestrator(auto_register=True)
