"""
Integration tests for AgentLoop.solve() method.

Tests the full plan-execute-verify loop with mocked Planner, Verifier,
and git operations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from scrappy.agent.agent_loop import AgentLoop
from scrappy.agent.types import (
    ActionResult,
    AgentContext,
)
from scrappy.agent.models import (
    Plan,
    Step,
    VerificationResult,
    VerificationPolicy,
    ApprovalPolicy,
)
from scrappy.agent.exceptions import (
    PlanRejectedError,
)
from scrappy.agent_config import AgentConfig



def _make_mock_undo_state(ref_suffix='abc123def456'):
    """Create a mock UndoState object for testing."""
    mock_state = Mock()
    mock_state.ref = f'refs/scrappy/undo/{ref_suffix}'
    return mock_state

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator adapter."""
    mock = Mock(spec=['delegate', 'list_providers'])
    response = Mock()
    response.content = '{"thought": "test", "action": "read_file", "parameters": {"path": "test.py"}}'
    response.provider = "openai"
    response.tool_calls = None
    mock.delegate.return_value = response
    return mock


@pytest.fixture
def mock_action_executor():
    """Create a mock action executor that succeeds by default."""
    mock = Mock()
    mock.execute.return_value = ActionResult(
        success=True,
        output="File written successfully",
        action="write_file",
        parameters={"path": "test.py", "content": "# test"},
        approved=True,
        executed=True,
    )
    return mock


@pytest.fixture
def mock_response_parser():
    """Create a mock response parser."""
    mock = Mock()
    mock.parse.return_value = Mock(
        thought="test thought",
        action="read_file",
        parameters={"path": "test.py"},
        is_complete=False,
        result_text="",
        additional_actions=[],
    )
    return mock


@pytest.fixture
def mock_ui():
    """Create a mock UI with all required methods."""
    mock = Mock()
    mock.show_progress = Mock()
    mock.show_info = Mock()
    mock.show_warning = Mock()
    mock.show_error = Mock()
    mock.show_rule = Mock()
    mock.confirm = Mock(return_value=True)  # Default to approving
    mock.show_provider_status = Mock()
    mock.reset_step_counter = Mock()
    return mock


@pytest.fixture
def mock_tool_registry():
    """Create a mock tool registry."""
    mock = Mock()
    mock.to_openai_schema.return_value = []
    return mock


@pytest.fixture
def mock_provider_strategy():
    """Create a mock provider strategy."""
    mock = Mock()
    mock.get_planner.return_value = "openai"
    mock.get_executor.return_value = "openai"
    mock.supports_dynamic_selection.return_value = True
    return mock


@pytest.fixture
def mock_context_factory():
    """Create a mock context factory."""
    mock = Mock()
    mock.build_context.return_value = AgentContext(
        system_prompt="Test system prompt",
        active_tools=["read_file", "write_file"],
        passive_rag_context="",
    )
    mock.build_hud_message = Mock(return_value=None)
    return mock


@pytest.fixture
def mock_config():
    """Create a mock agent config."""
    config = Mock(spec=AgentConfig)
    config.max_iterations = 50
    config.default_max_tokens = 4000
    config.default_temperature = 0.7
    config.meaningful_actions = ["write_file", "edit_file", "run_command"]
    return config


@pytest.fixture
def mock_planner():
    """Create a mock planner that returns a simple plan."""
    mock = AsyncMock()
    mock.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test goal",
        steps=[
            Step(
                id="step-1",
                description="Read the file",
                tool="read_file",
                parameters={"path": "test.py"},
                is_read_only=True,
            ),
            Step(
                id="step-2",
                description="Write the file",
                tool="write_file",
                parameters={"path": "test.py", "content": "# updated"},
                is_read_only=False,
            ),
        ],
    ))
    return mock


@pytest.fixture
def mock_verifier():
    """Create a mock verifier that passes by default."""
    mock = AsyncMock()
    mock.verify_step = AsyncMock(return_value=VerificationResult(
        success=True,
        message="Verification passed",
        files_checked=["test.py"],
    ))
    mock.verify_plan = AsyncMock(return_value=VerificationResult(
        success=True,
        message="Plan verification passed",
        files_checked=["test.py"],
    ))
    return mock


@pytest.fixture
def agent_loop(
    mock_orchestrator,
    mock_action_executor,
    mock_response_parser,
    mock_ui,
    mock_tool_registry,
    mock_provider_strategy,
    mock_context_factory,
    mock_config,
    mock_planner,
    mock_verifier,
):
    """Create an AgentLoop with mocked dependencies for integration testing."""
    return AgentLoop(
        orchestrator=mock_orchestrator,
        action_executor=mock_action_executor,
        response_parser=mock_response_parser,
        ui=mock_ui,
        tool_registry=mock_tool_registry,
        provider_strategy=mock_provider_strategy,
        config=mock_config,
        context_factory=mock_context_factory,
        planner=mock_planner,
        verifier=mock_verifier,
        verification_policy=VerificationPolicy(),
        approval_policy=ApprovalPolicy(),
    )


# =============================================================================
# Test: Full solve() Flow
# =============================================================================


@pytest.mark.asyncio
async def test_solve_full_flow_success(agent_loop, mock_planner, mock_ui):
    """Test successful execution of full solve() flow."""
    # Mock git checkpoint to avoid real git operations
    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123def456")

        result = await agent_loop.solve("Write a test file")

    # Verify plan was created
    mock_planner.create_plan.assert_called_once_with("Write a test file", None)

    # Verify approval was requested
    mock_ui.confirm.assert_called()

    # Verify success
    assert result["success"] is True
    assert result["stop_reason"] == "completed"
    assert len(result["completed_steps"]) == 2
    assert len(result["failed_steps"]) == 0
    assert "plan" in result


@pytest.mark.asyncio
async def test_solve_with_context(agent_loop, mock_planner):
    """Test solve() passes context to planner."""
    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Fix the bug", context="Error: IndexError at line 42")

    mock_planner.create_plan.assert_called_once_with(
        "Fix the bug",
        "Error: IndexError at line 42"
    )


# =============================================================================
# Test: Plan Approval
# =============================================================================


@pytest.mark.asyncio
async def test_solve_plan_rejected(agent_loop, mock_ui):
    """Test that rejecting a plan raises PlanRejectedError."""
    mock_ui.confirm.return_value = False

    with pytest.raises(PlanRejectedError) as exc_info:
        await agent_loop.solve("Do something")

    assert "User declined to execute plan" in str(exc_info.value)


@pytest.mark.asyncio
async def test_solve_plan_approval_shows_steps(agent_loop, mock_ui, mock_planner):
    """Test that plan approval displays all steps to user."""
    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Test task")

    # Verify plan details were shown
    mock_ui.show_rule.assert_called()
    mock_ui.show_info.assert_called()

    # Verify at least the goal was shown
    info_calls = [str(call) for call in mock_ui.show_info.call_args_list]
    assert any("Goal:" in str(call) for call in info_calls)


# =============================================================================
# Test: Step Failure and Retry
# =============================================================================


@pytest.mark.asyncio
async def test_solve_step_failure_triggers_retry(agent_loop, mock_verifier, mock_ui):
    """Test that step verification failure triggers retry."""
    # First call fails, second succeeds
    mock_verifier.verify_step = AsyncMock(side_effect=[
        VerificationResult(success=False, message="Lint error"),
        VerificationResult(success=True, message="Passed"),
    ])

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await agent_loop.solve("Write code")

    # Verify warning was shown
    mock_ui.show_warning.assert_called()
    warning_calls = [str(call) for call in mock_ui.show_warning.call_args_list]
    assert any("verification failed" in str(call).lower() for call in warning_calls)

    # Should still complete successfully after retry
    assert result["success"] is True


@pytest.mark.asyncio
async def test_solve_max_retries_exceeded_abort(
    agent_loop, mock_verifier, mock_ui, mock_action_executor
):
    """Test escape hatch when max retries exceeded - abort option."""
    # All verification attempts fail
    mock_verifier.verify_step = AsyncMock(return_value=VerificationResult(
        success=False,
        message="Persistent lint error",
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo, \
         patch('builtins.input', return_value="a"):  # User chooses abort
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await agent_loop.solve("Write code")

    assert result["success"] is False
    assert result["stop_reason"] == "abort"
    assert len(result["failed_steps"]) > 0


@pytest.mark.asyncio
async def test_solve_max_retries_exceeded_skip(
    agent_loop, mock_verifier, mock_ui, mock_planner
):
    """Test escape hatch when max retries exceeded - skip option."""
    # Create a plan with a single modifying step
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test goal",
        steps=[
            Step(
                id="step-1",
                description="Write the file",
                tool="write_file",
                parameters={"path": "test.py", "content": "# test"},
                is_read_only=False,
            ),
        ],
    ))

    # All verification attempts fail
    mock_verifier.verify_step = AsyncMock(return_value=VerificationResult(
        success=False,
        message="Persistent error",
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo, \
         patch('builtins.input', return_value="s"):  # User chooses skip
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await agent_loop.solve("Write code")

    # Step should be skipped, not failed
    assert result["stop_reason"] in ("completed", "partial_success")


@pytest.mark.asyncio
async def test_solve_max_retries_exceeded_rollback(
    agent_loop, mock_verifier, mock_ui, mock_planner
):
    """Test escape hatch when max retries exceeded - rollback option."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test goal",
        steps=[
            Step(
                id="step-1",
                description="Write the file",
                tool="write_file",
                parameters={"path": "test.py", "content": "# test"},
                is_read_only=False,
            ),
        ],
    ))

    mock_verifier.verify_step = AsyncMock(return_value=VerificationResult(
        success=False,
        message="Persistent error",
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo, \
         patch('scrappy.agent.agent_loop.undo_to_point') as mock_undo_fn, \
         patch('builtins.input', return_value="r"):  # User chooses rollback
        mock_undo.return_value = _make_mock_undo_state("abc123def456")
        # undo_to_point returns None on success (it modifies git state in place)

        result = await agent_loop.solve("Write code")

    # Should have attempted rollback via undo
    mock_undo_fn.assert_called()
    assert result["stop_reason"] == "rollback"


# =============================================================================
# Test: Partial Success
# =============================================================================


@pytest.mark.asyncio
async def test_solve_partial_success(agent_loop, mock_planner, mock_verifier, mock_ui):
    """Test partial success when some steps complete but others fail."""
    # Plan with 3 steps
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Multi-step task",
        steps=[
            Step(id="step-1", description="Step 1", tool="read_file",
                 parameters={"path": "a.py"}, is_read_only=True),
            Step(id="step-2", description="Step 2", tool="write_file",
                 parameters={"path": "b.py", "content": "#"}, is_read_only=False),
            Step(id="step-3", description="Step 3", tool="write_file",
                 parameters={"path": "c.py", "content": "#"}, is_read_only=False),
        ],
    ))

    # First modifying step (step-2) passes, second modifying step (step-3) always fails
    # This function checks which step is being verified by looking at the step parameter
    async def verify_side_effect(step, files):
        if step.id == "step-2":
            return VerificationResult(success=True, message="Passed")
        # step-3 always fails
        return VerificationResult(success=False, message="Failed")

    mock_verifier.verify_step = AsyncMock(side_effect=verify_side_effect)

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo, \
         patch('builtins.input', return_value="a"):  # User aborts on failure
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await agent_loop.solve("Multi-step task")

    # Should have partial success (step-1 read-only, step-2 passed, step-3 failed)
    assert result["success"] is False
    assert result["stop_reason"] == "abort"
    # step-1 (read-only) and step-2 (passed verification) should be completed
    assert len(result["completed_steps"]) == 2
    # step-3 should have failed
    assert len(result["failed_steps"]) == 1
    assert "summary" in result


# =============================================================================
# Test: Git Checkpoints
# =============================================================================


@pytest.mark.asyncio
async def test_solve_creates_checkpoints_for_modifying_steps(agent_loop, mock_planner):
    """Test that git checkpoints are created before modifying steps."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test",
        steps=[
            Step(id="step-1", description="Read", tool="read_file",
                 parameters={"path": "a.py"}, is_read_only=True),
            Step(id="step-2", description="Write", tool="write_file",
                 parameters={"path": "b.py", "content": "#"}, is_read_only=False),
        ],
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123def")

        await agent_loop.solve("Test")

    # Checkpoint should be called for initial + the modifying step
    assert mock_undo.call_count >= 1


@pytest.mark.asyncio
async def test_solve_no_checkpoint_for_read_only_steps(agent_loop, mock_planner):
    """Test that git checkpoints are NOT created for read-only steps."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Read files",
        steps=[
            Step(id="step-1", description="Read A", tool="read_file",
                 parameters={"path": "a.py"}, is_read_only=True),
            Step(id="step-2", description="Read B", tool="read_file",
                 parameters={"path": "b.py"}, is_read_only=True),
        ],
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Read files")

    # Checkpoint only called once for initial checkpoint
    # (which is created for the synthetic "initial" step)
    assert mock_undo.call_count == 1


# =============================================================================
# Test: Verification
# =============================================================================


@pytest.mark.asyncio
async def test_solve_runs_step_verification(agent_loop, mock_verifier, mock_planner):
    """Test that verification is run after modifying steps."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test",
        steps=[
            Step(id="step-1", description="Write", tool="write_file",
                 parameters={"path": "test.py", "content": "#"}, is_read_only=False),
        ],
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Test")

    # Step verification should be called
    mock_verifier.verify_step.assert_called()


@pytest.mark.asyncio
async def test_solve_runs_final_plan_verification(agent_loop, mock_verifier):
    """Test that final plan verification is run after all steps complete."""
    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Test")

    # Plan verification should be called at the end
    mock_verifier.verify_plan.assert_called()


@pytest.mark.asyncio
async def test_solve_skips_verification_for_read_only_steps(
    agent_loop, mock_verifier, mock_planner
):
    """Test that verification is skipped for read-only steps."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Read files",
        steps=[
            Step(id="step-1", description="Read", tool="read_file",
                 parameters={"path": "test.py"}, is_read_only=True),
        ],
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Read files")

    # Step verification should NOT be called for read-only step
    mock_verifier.verify_step.assert_not_called()


# =============================================================================
# Test: Error Cases
# =============================================================================


@pytest.mark.asyncio
async def test_solve_requires_planner():
    """Test that solve() raises error if planner not configured."""
    # Create agent loop without planner
    loop = AgentLoop(
        orchestrator=Mock(),
        action_executor=Mock(),
        response_parser=Mock(),
        ui=Mock(),
        tool_registry=Mock(),
        provider_strategy=Mock(),
        config=Mock(max_iterations=50, meaningful_actions=[]),
        context_factory=Mock(),
        planner=None,  # No planner
    )

    with pytest.raises(ValueError) as exc_info:
        await loop.solve("Do something")

    assert "Planner is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_solve_handles_step_execution_error(
    agent_loop, mock_action_executor, mock_planner, mock_ui
):
    """Test that step execution errors are handled properly."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test",
        steps=[
            Step(id="step-1", description="Run command", tool="run_command",
                 parameters={"command": "invalid_cmd"}, is_read_only=False),
        ],
    ))

    # Make execution fail
    mock_action_executor.execute.return_value = ActionResult(
        success=False,
        output="Command failed: not found",
        action="run_command",
        parameters={"command": "invalid_cmd"},
        approved=True,
        executed=True,
    )

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo, \
         patch('builtins.input', return_value="a"):  # User aborts on failure
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await agent_loop.solve("Test")

    assert result["success"] is False
    assert len(result["failed_steps"]) > 0


# =============================================================================
# Test: Progress Display
# =============================================================================


@pytest.mark.asyncio
async def test_solve_shows_step_progress(agent_loop, mock_ui, mock_planner):
    """Test that step progress is displayed during execution."""
    mock_planner.create_plan = AsyncMock(return_value=Plan(
        id="plan-test",
        goal="Test",
        steps=[
            Step(id="step-1", description="First step", tool="read_file",
                 parameters={"path": "a.py"}, is_read_only=True),
            Step(id="step-2", description="Second step", tool="read_file",
                 parameters={"path": "b.py"}, is_read_only=True),
        ],
    ))

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        await agent_loop.solve("Test")

    # Verify progress messages were shown
    progress_calls = [str(call) for call in mock_ui.show_progress.call_args_list]
    assert any("[Step 1/2]" in str(call) for call in progress_calls)
    assert any("[Step 2/2]" in str(call) for call in progress_calls)


# =============================================================================
# Test: No Verifier
# =============================================================================


@pytest.mark.asyncio
async def test_solve_works_without_verifier(mock_planner, mock_ui):
    """Test that solve() works when no verifier is configured."""
    loop = AgentLoop(
        orchestrator=Mock(),
        action_executor=Mock(execute=Mock(return_value=ActionResult(
            success=True, output="Done", action="write_file",
            parameters={}, approved=True, executed=True
        ))),
        response_parser=Mock(),
        ui=mock_ui,
        tool_registry=Mock(),
        provider_strategy=Mock(),
        config=Mock(max_iterations=50, meaningful_actions=[]),
        context_factory=Mock(),
        planner=mock_planner,
        verifier=None,  # No verifier
    )

    with patch('scrappy.agent.agent_loop.create_undo_point') as mock_undo:
        mock_undo.return_value = _make_mock_undo_state("abc123")

        result = await loop.solve("Test")

    # Should complete without verification
    assert result["success"] is True
    assert "verification_result" not in result or result["verification_result"] is None
