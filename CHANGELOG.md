# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [1.2.0] - 2026-01-20

### Features

- **Pluggable embedding models**: Embedding model is now configurable via `EmbeddingModelProtocol`. Supports swapping between different embedding providers without code changes.
- **Real-time token metrics**: Status bar now displays live token usage (input/output tokens, session total, context utilization percentage) during agent runs.
- **AGENTS.md project rules**: Agent now loads project-specific rules from `AGENTS.md` file, allowing per-project customization of agent behavior.
- **System reminders**: Added reminder injection to prevent context drift during long conversations. Reminders are automatically inserted based on conversation state.
- **Improved RAG context**: RAG results now include language hints and pattern notes for better code understanding.

### Bug Fixes

- Fixed token metrics not updating in TUI status bar after LLM responses
- Fixed test isolation issue where mock token env vars bled between test files

### Miscellaneous

- Excluded flaky TUI pilot tests from CI (still run locally)
- Updated CLI documentation to reflect current commands and architecture

## [1.1.0] - 2026-01-17

### Features

- Migrated agent to LangGraph-based architecture with distinct Think, Execute, Verify, Confirm, and Error nodes. This provides cleaner control flow, better error recovery, and more predictable behavior.
- Added Docker sandbox support for isolated command execution. Commands run in a container with project directory mounted, providing network isolation and timeout enforcement. Falls back to host execution if Docker is unavailable.
- Added Langfuse integration for agent observability. All graph invocations are traced with node execution flow visible for debugging.
- Agent can now be cancelled with Escape key during execution
- Agent mode now checks for git availability before running
- Agent dry-run mode is now opt-in via --dry-run flag instead of prompting every time
- Audit log now captures LLM thinking/reasoning for each action, increased result length to 5000 chars
- Agent output now uses compact mode by default, showing one-line summaries per action instead of verbose output
- Conversation history with SQLite persistence, token-budgeted recall, and session staleness detection
- First-run disclaimer banner requiring user acknowledgment before use
- LiteLLM provider abstraction for unified multi-provider support
- Streaming responses via LiteLLM integration
- Added force cancel with double-escape - press Escape twice quickly to immediately terminate agent execution
- Status bar now displays the current provider and model during agent runs
- Added MockLLMService for deterministic testing (set SCRAPPY_MOCK_LLM=1 to bypass wizard)
- Added Textual native testing framework replacing Docker-based e2e tests (10x faster, cross-platform)
- Setup wizard now supports managing multiple API keys and switching providers

### Bug Fixes

- Fixed agent rate limit handling: fallback chain now activates on any rate limit error. This ensures deterministic model fallback order instead of random Router selection.
- Fixed mouse selection and scrolling breaking after app initialization
- Fixed app hanging on exit by properly cancelling background tasks and shutting down Langfuse tracer
- Fixed escape key crash due to stale cancellation token check
- Fixed agent cancellation not working during confirmation prompts
- Fixed Groq rate limit handling
- Fixed model selector fallback behavior
- Fixed multiline input handling
- Fixed parser issues with triple quotes and truncated JSON

### Miscellaneous

- Removed ~48,000 lines of legacy code through LangGraph migration (deleted task_router/, agent/, and associated tests). Codebase is significantly simpler while retaining all features.
- Removed unused dependencies: rich-rst, tqdm, pandas, prompt_toolkit, langchain
- Added pytest integration test markers for better test organization
