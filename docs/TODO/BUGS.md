## Issues 

---
Problem: No output from chat. Output is literally: "|"
EG:
 Verbose mode: ON
   Metadata (provider, tokens, time) will be shown for responses.

 > how would we add rag to this codebase?

 Task Classification:
   Type: research
   Confidence: 1.00
   Complexity: 2/10
   Reasoning: Information gathering task: question, question_mark
   Provider: cerebras (llama3.1-8b) (hint: fast)
   Executing with: ResearchExecutor

 |
   cerebras (llama3.1-8b) | 641 tokens | 0.7ms
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
code search tool is completely useless -- maybe it's fine as a hybrid with grep/rg + semantic search
---

---
shift selection is messed up, can't 'unselect' once a point is selected.
---

===

Unconfirmed / Mixed Behavior
----