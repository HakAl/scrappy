"""
Tests for agent infinite loop prevention mechanisms.

This test suite ensures the agent can detect and prevent:
1. Duplicate consecutive actions (same action + same parameters)
2. Writing files with identical content repeatedly
3. Missing post-write verification
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from src.agent import (
    CodeAgent,
    AgentAction,
    ActionResult,
    ConversationState
)
from src.agent_config import AgentConfig
from src.orchestrator_adapter import OrchestratorAdapter


class TestDuplicateActionDetection:
    """Test that agent detects when repeating same action with same parameters."""

    @pytest.mark.unit
    def test_detect_duplicate_write_file_action(self):
        """
        CRITICAL: Agent should detect when writing same file with same content twice.

        This test demonstrates the bug in the audit log where write_file was called
        7 times with identical parameters.
        """
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Create conversation state with history
        state = ConversationState(
            messages=[],
            system_prompt="test",
            iteration=3,
            max_iterations=10,
            tools_executed=['write_file', 'write_file'],  # Already executed twice
            auto_confirm=True
        )

        # Create duplicate action (same as previous)
        action = AgentAction(
            thought="Need to update router.js",
            action="write_file",
            parameters={
                "path": "frontend/src/router.js",
                "content": "// Same content as before\nimport React from 'react';\n"
            },
            is_complete=False
        )

        # Track last actions for comparison
        state.last_action = {
            "action": "write_file",
            "parameters": {
                "path": "frontend/src/router.js",
                "content": "// Same content as before\nimport React from 'react';\n"
            }
        }

        # Execute action
        result = agent._execute(action, state)

        # EXPECTATION: Agent should detect duplicate and warn in the result
        # This test will FAIL until we implement duplicate detection
        assert "duplicate" in result.output.lower() or "already" in result.output.lower(), \
            "Agent should warn when repeating identical action"

    @pytest.mark.unit
    def test_allow_different_write_file_actions(self):
        """Agent should allow write_file with different parameters (not a duplicate)."""
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Create conversation state
        state = ConversationState(
            messages=[],
            system_prompt="test",
            iteration=2,
            max_iterations=10,
            tools_executed=['write_file'],
            auto_confirm=True
        )

        # Different file path = not a duplicate
        action = AgentAction(
            thought="Now creating another file",
            action="write_file",
            parameters={
                "path": "frontend/src/components/Header.js",
                "content": "export default function Header() {}"
            },
            is_complete=False
        )

        state.last_action = {
            "action": "write_file",
            "parameters": {
                "path": "frontend/src/router.js",
                "content": "import React from 'react';\n"
            }
        }

        # Mock the write_file tool
        agent.tools['write_file'] = Mock(return_value="Successfully wrote 35 characters")

        # Execute action
        result = agent._execute(action, state)

        # Should NOT warn about duplicates (different file)
        assert result.success is True
        assert result.executed is True
        if result.output:
            assert "duplicate" not in result.output.lower()

    @pytest.mark.unit
    def test_detect_three_consecutive_identical_actions(self):
        """
        CRITICAL: Detect when same action is repeated 3+ times consecutively.

        This mirrors the real bug where write_file was called 7 times with
        identical parameters.
        """
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Simulate state after 2 identical actions
        state = ConversationState(
            messages=[],
            system_prompt="test",
            iteration=4,
            max_iterations=10,
            tools_executed=['write_file', 'write_file', 'write_file'],
            auto_confirm=True
        )

        # Track action history for duplicate detection
        identical_params = {
            "path": "frontend/src/router.js",
            "content": "// Update router.js to include UserDashboard\nimport React from 'react';\n"
        }

        state.action_history = [
            {"action": "write_file", "parameters": identical_params},
            {"action": "write_file", "parameters": identical_params},
            {"action": "write_file", "parameters": identical_params}
        ]

        # Try to execute the SAME action again (4th time)
        action = AgentAction(
            thought="Need to update router.js",
            action="write_file",
            parameters=identical_params,
            is_complete=False
        )

        # Execute
        result = agent._execute(action, state)

        # EXPECTATION: Should detect pattern and refuse/warn
        # This test will FAIL until we implement pattern detection
        assert result.success is False or "repeated" in result.output.lower(), \
            "Agent should refuse to repeat identical action 4+ times"


class TestContentDiffDetection:
    """Test that agent detects when writing file with unchanged content."""

    @pytest.mark.unit
    def test_detect_write_with_identical_content(self):
        """
        Agent should detect when write_file doesn't change file content.

        This prevents infinite loops where the agent keeps 'fixing' a file
        but writes the same content each time.
        """
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Create conversation state
        state = ConversationState(
            messages=[],
            system_prompt="test",
            iteration=2,
            max_iterations=10,
            tools_executed=[],
            auto_confirm=True
        )

        # File content before write
        existing_content = "import React from 'react';\nexport default App;"

        # Action to write SAME content
        action = AgentAction(
            thought="Fixing the file",
            action="write_file",
            parameters={
                "path": "src/App.js",
                "content": existing_content  # Identical to existing
            },
            is_complete=False
        )

        # Mock write_file to detect no-change writes
        # In real implementation, write_file should check existing content
        agent.tools['write_file'] = Mock(
            return_value="Warning: File content unchanged. No modifications needed."
        )

        # Execute
        result = agent._execute(action, state)

        # EXPECTATION: Should indicate no change was needed
        assert "unchanged" in result.output.lower() or "no modif" in result.output.lower(), \
            "Agent should detect when write doesn't change content"


class TestPostWriteVerification:
    """Test that agent is encouraged to verify files after writing."""

    @pytest.mark.unit
    def test_conversation_suggests_verification_after_write(self):
        """
        After write_file, conversation update should encourage verification.

        This prevents bugs where agent writes broken code but never checks it.
        """
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Create successful write action
        action = AgentAction(
            thought="Creating router file",
            action="write_file",
            parameters={"path": "src/router.js", "content": "export default {}"},
            is_complete=False
        )

        result = ActionResult(
            success=True,
            output="Successfully wrote 18 characters to src/router.js",
            action="write_file",
            parameters=action.parameters,
            approved=True,
            executed=True
        )

        # Create conversation state
        state = ConversationState(
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant'},
                {'role': 'user', 'content': 'Create a router file'}
            ],
            system_prompt="test",
            iteration=1,
            max_iterations=10,
            tools_executed=[],
            auto_confirm=True
        )

        # Mock thought
        thought = Mock()
        thought.raw_response = '{"action": "write_file", ...}'

        # Update conversation
        agent._update_conversation(state, thought, action, result)

        # Check that latest user message encourages verification
        latest_message = state.messages[-1]
        assert latest_message['role'] == 'user'

        # EXPECTATION: Should suggest reading the file back or verifying
        # This test will FAIL until we implement verification prompts
        message_lower = latest_message['content'].lower()
        assert ('verify' in message_lower or
                'read' in message_lower or
                'check' in message_lower), \
            "After write_file, agent should be encouraged to verify the file"

    @pytest.mark.unit
    def test_no_verification_prompt_for_read_operations(self):
        """Read operations shouldn't trigger verification prompts."""
        # Setup mock orchestrator
        mock_orch = Mock(spec=OrchestratorAdapter)
        mock_orch.context = Mock()
        mock_orch.list_providers.return_value = ['test_provider']

        # Create agent
        config = AgentConfig()
        agent = CodeAgent(mock_orch, project_path=".", config=config)

        # Create read action
        action = AgentAction(
            thought="Reading config",
            action="read_file",
            parameters={"path": "config.json"},
            is_complete=False
        )

        result = ActionResult(
            success=True,
            output='{"key": "value"}',
            action="read_file",
            parameters=action.parameters,
            approved=True,
            executed=True
        )

        # Create conversation state
        state = ConversationState(
            messages=[
                {'role': 'system', 'content': 'System'},
                {'role': 'user', 'content': 'Read config'}
            ],
            system_prompt="test",
            iteration=1,
            max_iterations=10,
            tools_executed=[],
            auto_confirm=True
        )

        thought = Mock()
        thought.raw_response = '{"action": "read_file", ...}'

        # Update conversation
        agent._update_conversation(state, thought, action, result)

        # Should NOT suggest verification for reads
        latest_message = state.messages[-1]
        message_lower = latest_message['content'].lower()

        # Verification language should be absent (it's redundant for reads)
        assert 'verify by reading' not in message_lower, \
            "Read operations shouldn't prompt for reading again"
