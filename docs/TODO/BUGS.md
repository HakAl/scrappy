## Issues

---
src/agent/core.py -- _format_codebase_structure -- does this belong here?
---

---
Problem: Provider output is truncated.
EG:  Available Providers:
 --------------------------------------------------

 GITHUB
 (Active)
   Default Model: gpt-4o
   Daily Quota: 10,000 requests
   Daily Tokens: 10,000,000 TPD
   Models: gpt-4o, gpt-4o-mini, deepseek-r1
            ... and 6 more

 CEREBRAS
 (Active)
   Default Model: qwen-3-235b-a22b-instruct-2507
   Daily Quota: 14,400 requests
   Token Limit: 60,000 TPM
   Models: llama3.1-8b, llama-3.3-70b, qwen-3-32b
            ... and 1 more

 GROQ
 (Active)
   Default Model: llama-3.1-8b-instant
   Daily Quota: 7,000 requests
   Token Limit: 20,000 TPM
   Daily Tokens: 200,000 TPD
   Models: llama-3.1-8b-instant, llama-3.3-70b-versatile, llama-3.1-70b-versatile
            ... and 3 more

 GEMINI
 (Active)
   Default Model: gemini-2.5-flash-lite
   Daily Quota: 1,000 requests
   Daily Tokens: 250,000 TPD
   Models: gemini-2.5-flash-lite, gemini-2.0-flash-lite, gemini-2.0-flash
            ... and 2 more

 COHERE
 (Active)
   Default Model: command-r7b-12-2024
   Models: command-r-08-2024, command-r7b-12-2024, command-a-03-2025
            ... and 3 more



---

---
49 if TYPE_CHECKING
src/agent/agent_loop.py
src/agent/core.py
src/agent/provider_strategy.py
src/agent/system_prompt_builder.py
src/agent/types.py
src/agent/ui.py
src/agent_tools/components/subprocess_runner.py
src/agent_tools/formatters/output_formatter.py
src/agent_tools/tools/base.py
src/cli/agent_manager.py
src/cli/command_router.py
src/cli/context_commands.py
src/cli/core.py
src/cli/input_capture.py
src/cli/input_handler.py
src/cli/interactive.py
src/cli/interactive_banner.py
src/cli/mode_utils.py
src/cli/multiprovider.py
src/cli/output_bridge.py
src/cli/protocols.py
src/cli/task_router_handler.py
src/cli/textual_app.py
src/cli/textual_interactive.py
src/cli/types.py
src/cli/user_interaction.py
src/cli/utils/cli_factory.py
src/cli/utils/session_utils.py
src/context/augmenter.py
src/context/codebase_context.py
src/context/config_loader.py
src/context/semantic_manager.py
src/context/semantic/initializer.py
src/infrastructure/console_factory.py
src/infrastructure/output_mode.py
src/infrastructure/progress.py
src/infrastructure/protocols.py
src/infrastructure/textual_progress.py
src/infrastructure/formatters/cache_formatter.py
src/infrastructure/formatters/rate_limit_formatter.py
src/infrastructure/formatters/stats_formatter.py
src/orchestrator/cache.py
src/orchestrator/rate_limiting/calculator.py
src/orchestrator/rate_limiting/factory.py
src/orchestrator/rate_limiting/tracker.py
src/protocols/output.py
src/task_router/output_handler.py
src/task_router/protocols.py
---

---
shift selection is messed up, can't 'unselect' once a point is selected.
can't use mouse scroll during selection.  shift + scrolling
---

---
code search tool is completely useless (command tool has grep)-- more logical as a hybrid with grep/rg + semantic search?
---

===

Unconfirmed / Mixed Behavior
----