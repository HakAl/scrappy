"""
Smart query functionality for the CLI.
Provides research-first queries using tools to gather context.
"""

import click
from typing import Optional

from ..agent import CodeAgent
from ..intent_classifier import IntentClassifier, QueryIntent, get_research_actions
from .config.defaults import (
    TRUNCATE_RESEARCH_LARGE,
    TRUNCATE_RESEARCH_MEDIUM,
    TRUNCATE_FILE_CONTENT,
)
from .config.extensions import DEPENDENCY_FILES, CONFIGURATION_FILES
from .io_interface import CLIIOProtocol, ClickIO


class CLISmartQuery:
    """Handles smart queries with tool-based research."""

    def __init__(self, orchestrator):
        """Initialize smart query handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator
        self.classifier = IntentClassifier()

    def _safe_tool_call(self, tool_func, *args, **kwargs):
        """Safely call a tool function and handle errors.

        Wraps tool function calls in try/except to prevent research failures
        from crashing the entire smart query operation.

        Args:
            tool_func: The tool function to call.
            *args: Positional arguments to pass to tool_func.
            **kwargs: Keyword arguments to pass to tool_func.

        Returns:
            tuple: (success: bool, result: str)
                - success is True if the call succeeded and result has content
                - result is the tool output or error message
        """
        try:
            result = tool_func(*args, **kwargs)
            if result and "Error" not in str(result):
                return True, result
            return False, result
        except Exception as e:
            return False, f"Error: {str(e)}"

    def smart_query(self, query: str, io: Optional[CLIIOProtocol] = None):
        """Perform a smart query using tools to gather context before answering.

        Classifies the query intent, executes relevant research actions using
        code analysis tools, then generates an informed response with the
        gathered context.

        Supported intents include: file structure, code search, code explanation,
        git history, dependencies, architecture, bug investigation, testing,
        configuration, security, and documentation.

        Args:
            query: The user's question or query string.
            io: I/O interface for output. If None, uses ClickIO.

        State Changes:
            - Saves research results to orchestrator working memory
            - Adds discovery to orchestrator with query classification info

        Side Effects:
            - Writes progress messages to stdout via io
            - Reads files and searches codebase using CodeAgent tools
            - Makes LLM API call to generate response

        Returns:
            LLMResponse: The response object containing the answer, provider info,
                token usage, and latency.
        """
        if io is None:
            io = ClickIO()

        io.secho("\n[Smart Query] Analyzing intent...", fg="cyan", bold=True)

        # Classify the query intent
        classification = self.classifier.classify(query)

        # Display classification info
        io.echo(f"  Primary intent: {classification.primary_intent.intent.value} "
                f"(confidence: {classification.primary_intent.confidence:.2f})")

        if classification.secondary_intents:
            secondary_str = ", ".join([
                f"{i.intent.value}({i.confidence:.2f})"
                for i in classification.secondary_intents[:3]
            ])
            io.echo(f"  Secondary intents: {secondary_str}")

        if classification.entities:
            for entity_type, values in classification.entities.items():
                if values:
                    io.echo(f"  Extracted {entity_type}: {', '.join(values[:5])}")

        io.secho("\n[Smart Query] Researching...", fg="cyan", bold=True)

        # Create a research agent (read-only)
        agent = CodeAgent(self.orchestrator)

        # Gather context using tools based on the classification
        research_results = []
        tools_used = 0

        # Get recommended research actions
        actions = get_research_actions(classification)

        # Execute research based on intents and entities
        for action in actions:
            intent = action['intent']

            if intent == QueryIntent.FILE_STRUCTURE:
                io.echo("  - Checking directory structure...")
                try:
                    result = agent._tool_list_directory(".", depth=2)
                    if result and "Error" not in result:
                        research_results.append(f"Directory Structure:\n{result}")
                        tools_used += 1
                except Exception as e:
                    io.echo(f"    (Warning: Could not list directory: {e})")

            elif intent == QueryIntent.CODE_SEARCH:
                # Search for extracted entities first
                searched = set()

                # Search for class names
                for class_name in classification.entities.get('class_name', [])[:3]:
                    if class_name not in searched:
                        io.echo(f"  - Searching for class '{class_name}'...")
                        success, result = self._safe_tool_call(agent._tool_search_code, f"class {class_name}", "*.py")
                        if success and "No matches" not in result:
                            research_results.append(f"Class '{class_name}':\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                            tools_used += 1
                        searched.add(class_name)

                # Search for function names
                for func_name in classification.entities.get('function_name', [])[:3]:
                    if func_name not in searched:
                        io.echo(f"  - Searching for function '{func_name}'...")
                        success, result = self._safe_tool_call(agent._tool_search_code, f"def {func_name}", "*.py")
                        if success and "No matches" not in result:
                            research_results.append(f"Function '{func_name}':\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                            tools_used += 1
                        searched.add(func_name)

                # Search for keywords if no entities found
                if not searched and classification.keywords:
                    for keyword in classification.keywords[:3]:
                        if len(keyword) > 3:
                            io.echo(f"  - Searching for '{keyword}'...")
                            success, result = self._safe_tool_call(agent._tool_search_code, keyword, "*.py")
                            if success and "No matches" not in result:
                                research_results.append(f"Code containing '{keyword}':\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                                tools_used += 1
                                break

            elif intent == QueryIntent.CODE_EXPLANATION:
                # Read specific files if paths are extracted
                for file_path in classification.entities.get('file_path', [])[:2]:
                    io.echo(f"  - Reading file '{file_path}'...")
                    success, result = self._safe_tool_call(agent._tool_read_file, file_path, max_lines=100)
                    if success:
                        research_results.append(f"File '{file_path}':\n{result[:TRUNCATE_FILE_CONTENT]}")
                        tools_used += 1

            elif intent == QueryIntent.GIT_HISTORY:
                io.echo("  - Checking git history...")
                success, result = self._safe_tool_call(agent._tool_git_log, n=10)
                if success:
                    research_results.append(f"Recent Commits:\n{result}")
                    tools_used += 1

                # Also check git status
                io.echo("  - Checking git status...")
                success, result = self._safe_tool_call(agent._tool_git_status)
                if success:
                    research_results.append(f"Git Status:\n{result}")
                    tools_used += 1

            elif intent == QueryIntent.DEPENDENCY_INFO:
                io.echo("  - Checking dependencies...")
                # Check for common dependency files
                for dep_file in DEPENDENCY_FILES[:4]:
                    success, result = self._safe_tool_call(agent._tool_read_file, dep_file, max_lines=50)
                    if success and "not found" not in result.lower():
                        research_results.append(f"Dependencies ({dep_file}):\n{result}")
                        tools_used += 1
                        break

                # Search for specific package imports
                for pkg in classification.entities.get('package_name', [])[:3]:
                    io.echo(f"  - Searching for '{pkg}' usage...")
                    success, result = self._safe_tool_call(agent._tool_search_code, f"import {pkg}", "*.py")
                    if success and "No matches" not in result:
                        research_results.append(f"Usage of '{pkg}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}")
                        tools_used += 1

            elif intent == QueryIntent.ARCHITECTURE:
                io.echo("  - Analyzing project architecture...")
                success, result = self._safe_tool_call(agent._tool_list_directory, ".", depth=3)
                if success:
                    research_results.append(f"Project Structure:\n{result}")
                    tools_used += 1

                # Look for architectural patterns
                for pattern in ['service', 'controller', 'model', 'repository', 'handler']:
                    success, result = self._safe_tool_call(agent._tool_search_code, f"class.*{pattern}", "*.py")
                    if success and "No matches" not in result:
                        research_results.append(f"Architecture pattern '{pattern}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}")
                        tools_used += 1
                        break

            elif intent == QueryIntent.BUG_INVESTIGATION:
                # Search for error types mentioned
                for error_type in classification.entities.get('error_type', [])[:3]:
                    io.echo(f"  - Searching for '{error_type}'...")
                    success, result = self._safe_tool_call(agent._tool_search_code, error_type, "*.py")
                    if success and "No matches" not in result:
                        research_results.append(f"Error '{error_type}' occurrences:\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                        tools_used += 1

                # Check for error handling patterns
                if not classification.entities.get('error_type'):
                    io.echo("  - Searching for error handling...")
                    success, result = self._safe_tool_call(agent._tool_search_code, "except|raise|Error", "*.py")
                    if success and "No matches" not in result:
                        research_results.append(f"Error handling patterns:\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                        tools_used += 1

            elif intent == QueryIntent.TESTING:
                io.echo("  - Finding test files...")
                success, result = self._safe_tool_call(agent._tool_list_directory, ".", depth=3)
                if success:
                    # Filter for test directories/files
                    test_lines = [
                        line for line in result.split('\n')
                        if 'test' in line.lower()
                    ]
                    if test_lines:
                        research_results.append(f"Test files:\n" + '\n'.join(test_lines[:20]))
                        tools_used += 1

                # Search for test patterns
                io.echo("  - Searching for test patterns...")
                success, result = self._safe_tool_call(agent._tool_search_code, "def test_|class Test", "*.py")
                if success and "No matches" not in result:
                    research_results.append(f"Test definitions:\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                    tools_used += 1

            elif intent == QueryIntent.CONFIGURATION:
                io.echo("  - Checking configuration files...")
                for config_file in CONFIGURATION_FILES:
                    success, result = self._safe_tool_call(agent._tool_read_file, config_file, max_lines=100)
                    if success and "not found" not in result.lower():
                        research_results.append(f"Configuration ({config_file}):\n{result}")
                        tools_used += 1

                # Search for config usage
                io.echo("  - Searching for config usage...")
                success, result = self._safe_tool_call(agent._tool_search_code, "config|CONFIG|settings|Settings", "*.py")
                if success and "No matches" not in result:
                    research_results.append(f"Configuration usage:\n{result[:TRUNCATE_RESEARCH_LARGE]}")
                    tools_used += 1

            elif intent == QueryIntent.SECURITY:
                io.echo("  - Checking security patterns...")
                for pattern in ['auth', 'permission', 'token', 'password', 'encrypt']:
                    success, result = self._safe_tool_call(agent._tool_search_code, pattern, "*.py")
                    if success and "No matches" not in result:
                        research_results.append(f"Security pattern '{pattern}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}")
                        tools_used += 1
                        if tools_used >= 3:
                            break

            elif intent == QueryIntent.DOCUMENTATION:
                io.echo("  - Searching documentation...")
                success, result = self._safe_tool_call(agent._tool_list_directory, ".", depth=2)
                if success:
                    doc_lines = [
                        line for line in result.split('\n')
                        if any(ext in line.lower() for ext in ['.md', '.rst', '.txt', 'readme', 'doc'])
                    ]
                    if doc_lines:
                        research_results.append(f"Documentation files:\n" + '\n'.join(doc_lines[:15]))
                        tools_used += 1

        # Always include project summary if available
        if self.orchestrator.context.summary:
            research_results.insert(0, f"Project Summary:\n{self.orchestrator.context.summary}")

        io.echo(f"  - Gathered {tools_used} research results")

        # Build enhanced prompt with classification context
        classification_context = f"""Query Classification:
- Primary Intent: {classification.primary_intent.intent.value} (confidence: {classification.primary_intent.confidence:.2f})
- Key entities: {', '.join([f"{k}: {v}" for k, v in classification.entities.items() if v])}
- Keywords: {', '.join(classification.keywords[:10])}"""

        # Now answer with the gathered context
        if research_results:
            context = "\n\n---\n\n".join(research_results)
            prompt = f"""{classification_context}

Research Results:

{context}

---

User Question: {query}

Based on the classification and research findings above, provide a specific, accurate, and helpful answer. Reference specific files, functions, or code patterns when relevant."""
        else:
            prompt = f"""{classification_context}

User Question: {query}

Provide a helpful answer based on your understanding of the query intent."""

        io.secho("\nAssistant: ", fg="blue", bold=True, nl=False)
        response = self.orchestrator.delegate(
            self.orchestrator.brain,
            prompt,
            system_prompt="You are a helpful AI assistant with access to codebase research and query intent classification. Use the classification context and research findings to give specific, accurate answers. Always explain your reasoning based on the evidence found."
        )

        io.echo(response.content)
        io.secho(
            f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms | {tools_used} tools used]",
            fg="cyan"
        )

        # Save smart query research to working memory
        if tools_used > 0:
            self.orchestrator.working_memory.remember_search(
                f"smart_query: {query}",
                research_results[:5]  # Save top 5 research results
            )
            self.orchestrator.working_memory.add_discovery(
                f"Smart query '{query[:50]}...' classified as {classification.primary_intent.intent.value}, researched {tools_used} sources",
                "smart_query"
            )

        return response
