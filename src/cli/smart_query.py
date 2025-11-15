"""
Smart query functionality for the CLI.
Provides research-first queries using tools to gather context.
"""

import click

try:
    from ..agent import CodeAgent
    from ..intent_classifier import IntentClassifier, QueryIntent, get_research_actions
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent import CodeAgent
    from intent_classifier import IntentClassifier, QueryIntent, get_research_actions


class CLISmartQuery:
    """Handles smart queries with tool-based research."""

    def __init__(self, orchestrator):
        """Initialize smart query handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator
        self.classifier = IntentClassifier()

    def smart_query(self, query: str):
        """Perform a smart query using tools to gather context before answering.

        Returns:
            LLMResponse object with the answer
        """
        click.secho("\n[Smart Query] Analyzing intent...", fg="cyan", bold=True)

        # Classify the query intent
        classification = self.classifier.classify(query)

        # Display classification info
        click.echo(f"  Primary intent: {classification.primary_intent.intent.value} "
                   f"(confidence: {classification.primary_intent.confidence:.2f})")

        if classification.secondary_intents:
            secondary_str = ", ".join([
                f"{i.intent.value}({i.confidence:.2f})"
                for i in classification.secondary_intents[:3]
            ])
            click.echo(f"  Secondary intents: {secondary_str}")

        if classification.entities:
            for entity_type, values in classification.entities.items():
                if values:
                    click.echo(f"  Extracted {entity_type}: {', '.join(values[:5])}")

        click.secho("\n[Smart Query] Researching...", fg="cyan", bold=True)

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
                click.echo("  - Checking directory structure...")
                result = agent._tool_list_directory(".", depth=2)
                research_results.append(f"Directory Structure:\n{result}")
                tools_used += 1

            elif intent == QueryIntent.CODE_SEARCH:
                # Search for extracted entities first
                searched = set()

                # Search for class names
                for class_name in classification.entities.get('class_name', [])[:3]:
                    if class_name not in searched:
                        click.echo(f"  - Searching for class '{class_name}'...")
                        result = agent._tool_search_code(f"class {class_name}", "*.py")
                        if "No matches" not in result:
                            research_results.append(f"Class '{class_name}':\n{result[:1500]}")
                            tools_used += 1
                        searched.add(class_name)

                # Search for function names
                for func_name in classification.entities.get('function_name', [])[:3]:
                    if func_name not in searched:
                        click.echo(f"  - Searching for function '{func_name}'...")
                        result = agent._tool_search_code(f"def {func_name}", "*.py")
                        if "No matches" not in result:
                            research_results.append(f"Function '{func_name}':\n{result[:1500]}")
                            tools_used += 1
                        searched.add(func_name)

                # Search for keywords if no entities found
                if not searched and classification.keywords:
                    for keyword in classification.keywords[:3]:
                        if len(keyword) > 3:
                            click.echo(f"  - Searching for '{keyword}'...")
                            result = agent._tool_search_code(keyword, "*.py")
                            if "No matches" not in result:
                                research_results.append(f"Code containing '{keyword}':\n{result[:1500]}")
                                tools_used += 1
                                break

            elif intent == QueryIntent.CODE_EXPLANATION:
                # Read specific files if paths are extracted
                for file_path in classification.entities.get('file_path', [])[:2]:
                    click.echo(f"  - Reading file '{file_path}'...")
                    result = agent._tool_read_file(file_path, max_lines=100)
                    if "Error" not in result:
                        research_results.append(f"File '{file_path}':\n{result[:2000]}")
                        tools_used += 1

            elif intent == QueryIntent.GIT_HISTORY:
                click.echo("  - Checking git history...")
                result = agent._tool_git_log(n=10)
                research_results.append(f"Recent Commits:\n{result}")
                tools_used += 1

                # Also check git status
                click.echo("  - Checking git status...")
                result = agent._tool_git_status()
                research_results.append(f"Git Status:\n{result}")
                tools_used += 1

            elif intent == QueryIntent.DEPENDENCY_INFO:
                click.echo("  - Checking dependencies...")
                # Check for common dependency files
                for dep_file in ['requirements.txt', 'setup.py', 'pyproject.toml', 'package.json']:
                    result = agent._tool_read_file(dep_file, max_lines=50)
                    if "Error" not in result and "not found" not in result.lower():
                        research_results.append(f"Dependencies ({dep_file}):\n{result}")
                        tools_used += 1
                        break

                # Search for specific package imports
                for pkg in classification.entities.get('package_name', [])[:3]:
                    click.echo(f"  - Searching for '{pkg}' usage...")
                    result = agent._tool_search_code(f"import {pkg}", "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Usage of '{pkg}':\n{result[:1000]}")
                        tools_used += 1

            elif intent == QueryIntent.ARCHITECTURE:
                click.echo("  - Analyzing project architecture...")
                result = agent._tool_list_directory(".", depth=3)
                research_results.append(f"Project Structure:\n{result}")
                tools_used += 1

                # Look for architectural patterns
                for pattern in ['service', 'controller', 'model', 'repository', 'handler']:
                    result = agent._tool_search_code(f"class.*{pattern}", "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Architecture pattern '{pattern}':\n{result[:1000]}")
                        tools_used += 1
                        break

            elif intent == QueryIntent.BUG_INVESTIGATION:
                # Search for error types mentioned
                for error_type in classification.entities.get('error_type', [])[:3]:
                    click.echo(f"  - Searching for '{error_type}'...")
                    result = agent._tool_search_code(error_type, "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Error '{error_type}' occurrences:\n{result[:1500]}")
                        tools_used += 1

                # Check for error handling patterns
                if not classification.entities.get('error_type'):
                    click.echo("  - Searching for error handling...")
                    result = agent._tool_search_code("except|raise|Error", "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Error handling patterns:\n{result[:1500]}")
                        tools_used += 1

            elif intent == QueryIntent.TESTING:
                click.echo("  - Finding test files...")
                result = agent._tool_list_directory(".", depth=3)
                # Filter for test directories/files
                test_lines = [
                    line for line in result.split('\n')
                    if 'test' in line.lower()
                ]
                if test_lines:
                    research_results.append(f"Test files:\n" + '\n'.join(test_lines[:20]))
                    tools_used += 1

                # Search for test patterns
                click.echo("  - Searching for test patterns...")
                result = agent._tool_search_code("def test_|class Test", "*.py")
                if "No matches" not in result:
                    research_results.append(f"Test definitions:\n{result[:1500]}")
                    tools_used += 1

            elif intent == QueryIntent.CONFIGURATION:
                click.echo("  - Checking configuration files...")
                for config_file in ['config.py', 'settings.py', '.env.example', 'config.json', 'config.yaml']:
                    result = agent._tool_read_file(config_file, max_lines=100)
                    if "Error" not in result and "not found" not in result.lower():
                        research_results.append(f"Configuration ({config_file}):\n{result}")
                        tools_used += 1

                # Search for config usage
                click.echo("  - Searching for config usage...")
                result = agent._tool_search_code("config|CONFIG|settings|Settings", "*.py")
                if "No matches" not in result:
                    research_results.append(f"Configuration usage:\n{result[:1500]}")
                    tools_used += 1

            elif intent == QueryIntent.SECURITY:
                click.echo("  - Checking security patterns...")
                for pattern in ['auth', 'permission', 'token', 'password', 'encrypt']:
                    result = agent._tool_search_code(pattern, "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Security pattern '{pattern}':\n{result[:1000]}")
                        tools_used += 1
                        if tools_used >= 3:
                            break

            elif intent == QueryIntent.DOCUMENTATION:
                click.echo("  - Searching documentation...")
                result = agent._tool_list_directory(".", depth=2)
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

        click.echo(f"  - Gathered {tools_used} research results")

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

        click.secho("\nAssistant: ", fg="blue", bold=True, nl=False)
        response = self.orchestrator.delegate(
            self.orchestrator.brain,
            prompt,
            system_prompt="You are a helpful AI assistant with access to codebase research and query intent classification. Use the classification context and research findings to give specific, accurate answers. Always explain your reasoning based on the evidence found."
        )

        click.echo(response.content)
        click.secho(
            f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms | {tools_used} tools used]",
            fg="cyan"
        )

        # Save smart query research to working memory
        if tools_used > 0:
            self.orchestrator.remember_search(
                f"smart_query: {query}",
                research_results[:5]  # Save top 5 research results
            )
            self.orchestrator.add_discovery(
                f"Smart query '{query[:50]}...' classified as {classification.primary_intent.intent.value}, researched {tools_used} sources",
                "smart_query"
            )

        return response
