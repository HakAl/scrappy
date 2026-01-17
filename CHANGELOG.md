# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [1.1.0] - 2026-01-17

No significant changes.


## [1.1.0] - 2026-01-11

### Features

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

- Fixed mouse selection and scrolling breaking after app initialization
- Fixed app hanging on exit by properly cancelling background tasks and shutting down Langfuse tracer
- Fixed escape key crash due to stale cancellation token check
- Fixed agent cancellation not working during confirmation prompts
- Fixed Groq rate limit handling
- Fixed model selector fallback behavior
- Fixed multiline input handling
- Fixed parser issues with triple quotes and truncated JSON

### Miscellaneous

- Removed unused dependencies: rich-rst, tqdm, pandas, prompt_toolkit, langchain
- Added pytest integration test markers for better test organization
