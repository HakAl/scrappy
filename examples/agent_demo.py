#!/usr/bin/env python3
"""
Code Agent Demo - AI writes code with human approval.

This demonstrates:
1. Hybrid model approach (Gemini for planning, Cerebras for fast tasks)
2. Human-in-the-loop approval for all file operations
3. Git checkpoint and rollback
4. Audit logging
5. Safety features (sandboxing, dry-run mode)
"""

import sys
from pathlib import Path

# Add src to path
src_path = str(Path(__file__).parent.parent / 'src')
sys.path.insert(0, src_path)

# Import providers directly (avoids relative import issues)
from providers import (
    CerebrasProvider, GroqProvider, GeminiProvider, CohereProvider,
    ProviderRegistry, LLMResponse
)
from context import CodebaseContext
from agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint


# Create a minimal orchestrator for the demo (avoids import issues with orchestrator.py)
class DemoOrchestrator:
    """Minimal orchestrator for demo purposes."""

    def __init__(self):
        self.registry = ProviderRegistry()
        self.context = CodebaseContext()
        self.context_aware = True
        self._setup_providers()

    def _setup_providers(self):
        """Register available providers."""
        providers = [
            (CerebrasProvider, "Cerebras"),
            (GroqProvider, "Groq"),
            (GeminiProvider, "Gemini"),
        ]

        for ProviderClass, name in providers:
            try:
                self.registry.register(ProviderClass())
                print(f"[OK] {name} registered")
            except Exception as e:
                print(f"[X] {name}: {str(e)[:50]}")


# Alias for compatibility
AgentOrchestrator = DemoOrchestrator


def demo_agent_setup():
    """Demo 1: Setting up the code agent."""
    print("\n" + "=" * 60)
    print("DEMO 1: Code Agent Setup")
    print("=" * 60)

    # Create orchestrator
    orch = AgentOrchestrator()

    # Create agent
    agent = CodeAgent(orch)

    print(f"\nAgent Configuration:")
    print(f"  Planner (smart tasks): {agent.planner}")
    print(f"  Executor (fast tasks): {agent.executor}")
    print(f"  Project root: {agent.project_root}")
    print(f"  Dry-run mode: {agent.dry_run}")

    print(f"\nAvailable tools:")
    for tool_name in agent.tools.keys():
        print(f"  - {tool_name}")


def demo_tool_usage():
    """Demo 2: Direct tool usage."""
    print("\n" + "=" * 60)
    print("DEMO 2: Direct Tool Usage")
    print("=" * 60)

    orch = AgentOrchestrator()
    agent = CodeAgent(orch)

    # Test read_file
    print("\n--- Testing read_file ---")
    result = agent._tool_read_file("README.md")
    print(f"Read README.md: {len(result)} characters")
    print(f"First 100 chars: {result[:100]}...")

    # Test list_files
    print("\n--- Testing list_files ---")
    result = agent._tool_list_files(".", "*.py")
    print(f"Python files in project:")
    for line in result.split('\n')[:10]:
        print(f"  {line}")
    if result.count('\n') > 10:
        print("  ...")

    # Test search_code
    print("\n--- Testing search_code ---")
    result = agent._tool_search_code("def __init__", "*.py")
    print(f"Found __init__ methods:")
    for line in result.split('\n')[:5]:
        print(f"  {line}")

    # Test git_log
    print("\n--- Testing git_log ---")
    result = agent._tool_git_log(n=5)
    print(f"Recent commits:")
    for line in result.split('\n')[:5]:
        print(f"  {line}")

    # Test git_diff
    print("\n--- Testing git_diff ---")
    result = agent._tool_git_diff()
    if "No changes" in result:
        print(f"  {result}")
    else:
        print(f"  Changes found: {len(result)} chars")
        print(f"  First 200 chars: {result[:200]}...")


def demo_safety_features():
    """Demo 3: Safety features."""
    print("\n" + "=" * 60)
    print("DEMO 3: Safety Features")
    print("=" * 60)

    orch = AgentOrchestrator()
    agent = CodeAgent(orch)

    # Test path sandboxing
    print("\n--- Path Sandboxing ---")
    unsafe_path = "../../../etc/passwd"
    result = agent._tool_read_file(unsafe_path)
    print(f"Trying to read {unsafe_path}:")
    print(f"  Result: {result}")

    # Test dangerous command blocking
    print("\n--- Dangerous Command Blocking ---")
    dangerous_cmd = "rm -rf /"
    result = agent._tool_run_command(dangerous_cmd)
    print(f"Trying to run '{dangerous_cmd}':")
    print(f"  Result: {result}")

    # Test dry-run mode
    print("\n--- Dry-Run Mode ---")
    agent.dry_run = True
    result = agent._tool_write_file("test_file.txt", "test content")
    print(f"Writing file in dry-run mode:")
    print(f"  Result: {result}")
    agent.dry_run = False


def demo_audit_logging():
    """Demo 4: Audit logging."""
    print("\n" + "=" * 60)
    print("DEMO 4: Audit Logging")
    print("=" * 60)

    orch = AgentOrchestrator()
    agent = CodeAgent(orch)

    # Simulate some actions
    agent._log_action("read_file", {"path": "src/app.py"}, "File contents...", True)
    agent._log_action("write_file", {"path": "src/app.py", "content": "..."}, "Success", True)
    agent._log_action("run_command", {"command": "pytest"}, "All tests passed", True)

    print(f"\nAudit Log ({len(agent.audit_log)} entries):")
    for entry in agent.audit_log:
        status = "Approved" if entry['approved'] else "Denied"
        print(f"  [{entry['timestamp'][:19]}] {entry['action']} - {status}")
        print(f"    Parameters: {entry['parameters']}")


def demo_git_checkpoint():
    """Demo 5: Git checkpoint and rollback."""
    print("\n" + "=" * 60)
    print("DEMO 5: Git Checkpoint & Rollback")
    print("=" * 60)

    # Check if we're in a git repo
    print("\n--- Creating Checkpoint ---")
    checkpoint = create_git_checkpoint(".")

    if checkpoint:
        print(f"Checkpoint created: {checkpoint}")
        print(f"Short hash: {checkpoint[:8]}")
        print(f"\nTo rollback: git reset --hard {checkpoint}")
    else:
        print("Not in a git repository or git not available")

    print("\n--- Rollback Function ---")
    print("rollback_to_checkpoint(commit_hash, project_path)")
    print("  - Resets working directory to checkpoint")
    print("  - Returns True on success, False on failure")


def demo_agent_workflow():
    """Demo 6: Complete agent workflow (simulated)."""
    print("\n" + "=" * 60)
    print("DEMO 6: Agent Workflow (Simulated)")
    print("=" * 60)

    print("""
A typical agent workflow:

1. User initiates task:
   You: /agent Add error handling to API endpoints

2. Agent creates plan:
   [gemini] Thinking...
   Thought: I need to examine the current API structure

3. Agent requests file read:
   Agent wants to: read_file
   Parameters: {"path": "src/api.py"}
   Allow? [y/N]: y

4. Agent analyzes and plans changes:
   [gemini] Thinking...
   Thought: I'll add try-except blocks with proper error responses

5. Agent writes modified file:
   Agent wants to: write_file
   Parameters: {"path": "src/api.py", "content": "..."}
   Allow? [y/N]: y

6. Agent confirms completion:
   Result: Added error handling with proper HTTP status codes

7. User reviews and optionally rolls back:
   Rollback to checkpoint? [y/N]: n
""")

    print("Key Safety Points:")
    print("  - Every action requires explicit approval")
    print("  - Git checkpoint before any changes")
    print("  - Full audit trail saved to .scrappy/.audit.json")
    print("  - Easy rollback with git reset --hard")


def demo_programmatic_usage():
    """Demo 7: Programmatic agent usage."""
    print("\n" + "=" * 60)
    print("DEMO 7: Programmatic Usage")
    print("=" * 60)

    print("""
# In your code:

from src.orchestrator import AgentOrchestrator
from src.agent import CodeAgent, create_git_checkpoint

# Setup
orch = AgentOrchestrator(auto_explore=True)
agent = CodeAgent(orch)

# Create checkpoint
checkpoint = create_git_checkpoint(".")

# Run agent (with auto_confirm=False for safety)
result = agent.run(
    task="Add input validation to user endpoints",
    max_iterations=10,
    auto_confirm=False  # Human approves each action
)

# Check results
if result['success']:
    print(f"Task completed in {result['iterations']} iterations")
    print(f"Result: {result['result']}")
else:
    print(f"Task failed: {result['result']}")

# Save audit log
agent.save_audit_log()

# Optionally rollback
if not result['success']:
    rollback_to_checkpoint(checkpoint)
""")


def main():
    print("=" * 60)
    print("Code Agent Demo - AI Writes Code with Human Approval")
    print("=" * 60)

    # Run demos
    demo_agent_setup()
    demo_tool_usage()
    demo_safety_features()
    demo_audit_logging()
    demo_git_checkpoint()
    demo_agent_workflow()
    demo_programmatic_usage()

    print("\n" + "=" * 60)
    print("Demo Complete! Key Takeaways:")
    print("=" * 60)
    print("- Hybrid approach: Gemini for planning, Cerebras for speed")
    print("- Human-in-the-loop: Every action requires approval")
    print("- Safety first: Sandboxing, dangerous command blocking")
    print("- Full audit trail: All actions logged with timestamps")
    print("- Git integration: Checkpoint before changes, easy rollback")
    print("- Dry-run mode: Preview without making changes")

    print("\nRun the agent from CLI:")
    print("  python llm_team.py agent 'Add feature X'")
    print("  python llm_team.py agent 'Fix bug Y' --dry-run")

    print("\nOr in interactive mode:")
    print("  python llm_team.py")
    print("  You: /agent Implement rate limiting")
    print("=" * 60)


if __name__ == "__main__":
    main()
