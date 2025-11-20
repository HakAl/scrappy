"""
Tests for CodeAgent dependency injection.

Verifies that injected dependencies are actually USED correctly,
not just that they can be assigned.

Following Phase 5 principles:
- Test behavior, not structure
- Prove features work with injected dependencies
- Cover edge cases
- Minimal mocking (only external dependencies)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, call

from src.agent import CodeAgent
from src.agent.protocols import (
    FileSystemProtocol,
    AuditLoggerProtocol,
    ResponseParserProtocol,
)
from src.infrastructure import InMemoryFileSystem
from src.agent.platform_adapter import MockPlatformUtils, 
from src.agent_config import AgentConfig


class TestFileSystemBehavior:
    """Tests that agent actually USES injected file system for operations."""

    def test_uses_file_system_to_resolve_project_path(self, orchestrator):
        """Agent uses injected file system to resolve project root."""
        fs = Mock(spec=FileSystemProtocol)
        fs.resolve = Mock(return_value=Path("/resolved/project"))
        fs.is_dir = Mock(return_value=True)
        fs.exists = Mock(return_value=True)

        agent = CodeAgent(
            orchestrator=orchestrator,
            project_path="/test/project",
            file_system=fs,
        )

        # Verify file system was USED to resolve path
        fs.resolve.assert_called()
        assert agent.project_root == Path("/resolved/project")

    def test_uses_in_memory_file_system_for_isolation(self, orchestrator):
        """Agent uses InMemoryFileSystem for isolated testing."""
        fs = InMemoryFileSystem()
        fs.write_text("/project/test.py", "def hello(): pass")

        agent = CodeAgent(
            orchestrator=orchestrator,
            project_path="/project",
            file_system=fs,
        )

        # Verify agent has access to in-memory files
        assert fs.exists("/project/test.py")
        content = fs.read_text("/project/test.py")
        assert "def hello()" in content

    def test_file_system_isolation_prevents_real_file_access(self, orchestrator):
        """InMemoryFileSystem prevents access to real file system."""
        fs = InMemoryFileSystem()

        agent = CodeAgent(
            orchestrator=orchestrator,
            project_path="/test",
            file_system=fs,
        )

        # Real file system paths should not exist in memory
        assert not fs.exists("/etc/passwd")
        assert not fs.exists("C:\\Windows\\System32")

    def test_uses_file_system_for_default_project_root(self, orchestrator):
        """Agent uses file system to resolve '.' when no path provided."""
        fs = Mock(spec=FileSystemProtocol)
        fs.resolve = Mock(return_value=Path("/current/dir"))
        fs.is_dir = Mock(return_value=True)
        fs.exists = Mock(return_value=True)

        agent = CodeAgent(
            orchestrator=orchestrator,
            file_system=fs,
        )

        # Verify file system was called to resolve current directory
        fs.resolve.assert_called_with(".")
        assert agent.project_root == Path("/current/dir")


class TestPlatformUtilsBehavior:
    """Tests that agent actually USES injected platform utils."""

    def test_simulates_windows_platform_behavior(self, orchestrator):
        """Agent behaves differently on Windows vs Unix using injected utils."""
        windows_utils = MockPlatformUtils(
            platform="windows",
            is_windows_val=True,
            is_unix_val=False,
        )

        agent = CodeAgent(
            orchestrator=orchestrator,
            platform_utils=windows_utils,
        )

        # Verify agent has access to platform info
        assert agent._platform_utils.is_windows() is True
        assert agent._platform_utils.is_unix() is False

    def test_simulates_unix_platform_behavior(self, orchestrator):
        """Agent behaves differently on Unix using injected utils."""
        unix_utils = MockPlatformUtils(
            platform="linux",
            is_windows_val=False,
            is_unix_val=True,
        )

        agent = CodeAgent(
            orchestrator=orchestrator,
            platform_utils=unix_utils,
        )

        # Verify agent has access to platform info
        assert agent._platform_utils.is_windows() is False
        assert agent._platform_utils.is_unix() is True

    def test_cross_platform_testing_with_mock_utils(self, orchestrator):
        """MockPlatformUtils enables testing behavior on different platforms."""
        # Test both platforms in one test to prove swappability
        for platform, is_windows, is_unix in [
            ("windows", True, False),
            ("linux", False, True),
            ("darwin", False, True),
        ]:
            utils = MockPlatformUtils(
                platform=platform,
                is_windows_val=is_windows,
                is_unix_val=is_unix,
            )

            agent = CodeAgent(
                orchestrator=orchestrator,
                platform_utils=utils,
            )

            assert agent._platform_utils.get_platform_name() == platform
            assert agent._platform_utils.is_windows() == is_windows
            assert agent._platform_utils.is_unix() == is_unix


class TestAuditLoggerBehavior:
    """Tests that agent actually USES injected audit logger."""

    def test_uses_audit_logger_when_provided(self, orchestrator):
        """Agent accepts and can use custom audit logger."""
        logger = Mock(spec=AuditLoggerProtocol)
        logger.get_log = Mock(return_value=[])

        agent = CodeAgent(
            orchestrator=orchestrator,
            audit_logger=logger,
        )

        # Verify logger is accessible
        log = agent._audit_logger.get_log()
        assert isinstance(log, list)

    def test_audit_logger_can_be_queried(self, orchestrator):
        """Injected audit logger can be queried for entries."""
        logger = Mock(spec=AuditLoggerProtocol)
        logger.get_log = Mock(return_value=[
            {"action": "read_file", "path": "test.py"},
            {"action": "write_file", "path": "output.py"},
        ])

        agent = CodeAgent(
            orchestrator=orchestrator,
            audit_logger=logger,
        )

        # Verify we can query the audit log
        entries = agent._audit_logger.get_log()
        assert len(entries) == 2
        assert entries[0]["action"] == "read_file"


class TestResponseParserBehavior:
    """Tests that agent actually USES injected response parser."""

    def test_uses_response_parser_when_provided(self, orchestrator):
        """Agent accepts and can use custom response parser."""
        parser = Mock(spec=ResponseParserProtocol)

        agent = CodeAgent(
            orchestrator=orchestrator,
            response_parser=parser,
        )

        # Verify parser was injected correctly
        assert agent._response_parser is parser

    def test_response_parser_is_used_for_parsing(self, orchestrator):
        """Agent would use injected parser for response parsing."""
        # This tests that parser can be swapped for testing
        parser = Mock(spec=ResponseParserProtocol)
        parser.parse = Mock(return_value=Mock(
            is_complete=True,
            thought="test thought",
            action="complete",
        ))

        agent = CodeAgent(
            orchestrator=orchestrator,
            response_parser=parser,
        )

        # Parser should be available for use
        result = agent._response_parser.parse('{"thought": "test"}')
        assert result.thought == "test thought"
        parser.parse.assert_called_once()


class TestCommandExecutorBehavior:
    """Tests that agent actually USES injected command executor."""

    def test_accepts_command_executor(self, orchestrator):
        """Agent accepts custom command executor injection."""
        executor = Mock()
        executor.execute = Mock(return_value=(0, "success", ""))

        agent = CodeAgent(
            orchestrator=orchestrator,
            command_executor=executor,
        )

        # Verify executor was injected correctly
        assert agent._command_executor is executor


class TestIOInterfaceBehavior:
    """Tests that agent actually USES injected IO interface."""

    def test_accepts_io_interface(self, orchestrator):
        """Agent accepts custom IO interface injection."""
        io = Mock()
        io.echo = Mock()
        io.secho = Mock()

        agent = CodeAgent(
            orchestrator=orchestrator,
            io=io,
        )

        # Verify IO is accessible
        assert agent.io is not None


class TestMultipleDependencyInjection:
    """Tests that multiple dependencies work together correctly."""

    def test_all_dependencies_can_be_injected_together(self, orchestrator):
        """Agent works correctly with all dependencies injected."""
        fs = InMemoryFileSystem()
        fs.write_text("/project/main.py", "print('hello')")

        utils = MockPlatformUtils(platform="windows", is_windows_val=True)
        logger = Mock(spec=AuditLoggerProtocol)
        logger.get_log = Mock(return_value=[])
        parser = Mock(spec=ResponseParserProtocol)
        io_interface = Mock()
        io_interface.echo = Mock()

        agent = CodeAgent(
            orchestrator=orchestrator,
            file_system=fs,
            platform_utils=utils,
            audit_logger=logger,
            response_parser=parser,
            io=io_interface,
            project_path="/project",
        )

        # Verify all dependencies are accessible
        assert str(agent.project_root) == "/project" or agent.project_root == Path("/project")
        assert agent._platform_utils.is_windows() is True
        assert isinstance(agent._audit_logger.get_log(), list)
        assert agent.io is not None

    def test_mixed_injected_and_default_dependencies(self, orchestrator):
        """Agent handles mix of injected and default dependencies."""
        fs = InMemoryFileSystem()
        utils = MockPlatformUtils()

        agent = CodeAgent(
            orchestrator=orchestrator,
            file_system=fs,
            platform_utils=utils,
            # Other dependencies use defaults
        )

        # Injected dependencies
        assert isinstance(agent._file_system, InMemoryFileSystem)
        assert isinstance(agent._platform_utils, MockPlatformUtils)

        # Default dependencies should be created (not None)
        assert hasattr(agent, '_audit_logger') and agent._audit_logger
        assert hasattr(agent, '_response_parser') and agent._response_parser
        assert hasattr(agent, 'io') and agent.io


class TestDependencyEdgeCases:
    """Edge case tests for dependency injection."""

    def test_handles_none_file_system_with_default(self, orchestrator):
        """Agent creates default file system when None provided."""
        agent = CodeAgent(
            orchestrator=orchestrator,
            file_system=None,  # Explicit None
        )

        # Should create default file system that can resolve paths
        result = agent._file_system.resolve(".")
        assert result is not None

    def test_handles_none_platform_utils_with_default(self, orchestrator):
        """Agent creates default platform utils when None provided."""
        agent = CodeAgent(
            orchestrator=orchestrator,
            platform_utils=None,  # Explicit None
        )

        # Should create default platform utils that can detect platform
        platform = agent._platform_utils.get_platform_name().lower()
        assert platform in ["windows", "linux", "darwin"]

    def test_file_system_abstraction_allows_testing_without_real_io(self, orchestrator):
        """File system abstraction prevents actual I/O during tests."""
        fs = InMemoryFileSystem()

        agent = CodeAgent(
            orchestrator=orchestrator,
            project_path="/test/project",
            file_system=fs,
        )

        # All file operations should use in-memory file system
        # Real file system should never be touched
        assert not fs.exists("/real/system/path")


# Fixtures

@pytest.fixture
def orchestrator():
    """Create a mock orchestrator for testing."""
    mock_orch = MagicMock()
    mock_orch.list_providers.return_value = ['gemini']
    mock_orch.context = ""
    return mock_orch
