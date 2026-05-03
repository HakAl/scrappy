"""Tests for registry factory defaults and filtering."""

from scrappy.agent_tools.registry_factory import create_default_registry
from scrappy.agent_tools.tools.registry import ToolRegistry


class TestRegistryFactoryDefaults:
    """Tests for shared default registry construction."""

    def test_tool_registry_create_default_matches_factory_default(self):
        """Legacy ToolRegistry.create_default should match runtime defaults."""
        legacy = set(ToolRegistry.create_default().list_tools())
        runtime = set(create_default_registry().list_tools())

        assert legacy == runtime
        assert "complete" in legacy
        assert "run_command" in legacy

    def test_tool_registry_full_profile_includes_directory_listing(self):
        """Full profile should retain the broader exploratory tool set."""
        tools = set(ToolRegistry.create_default(profile="full").list_tools())

        assert "list_directory" in tools
        assert "task" in tools

    def test_create_default_registry_respects_include_flags(self):
        """include_web/include_git should remove optional tool groups."""
        tools = set(create_default_registry(include_web=False, include_git=False).list_tools())

        assert "web_fetch" not in tools
        assert "git_status" not in tools
        assert "git_diff" not in tools
        assert "read_file" in tools
        assert "complete" in tools
