"""
Tests for SystemPromptBuilder - context-aware system prompt construction.

The SystemPromptBuilder should:
1. Use CodebaseContext to detect project type (not duplicate detection)
2. Include ONLY relevant guidance for the current platform
3. Include ONLY relevant guidance for the detected project type
4. Be succinct - no bloated examples for irrelevant technologies
5. Provide accurate command guidance for the actual environment
"""
import pytest
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path

from src.context import CodebaseContext


class TestSystemPromptBuilderUsesCodebaseContext:
    """SystemPromptBuilder should leverage CodebaseContext for project detection."""

    @pytest.mark.unit
    def test_accepts_codebase_context_instance(self, temp_project_dir):
        """SystemPromptBuilder should accept a CodebaseContext instance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = SystemPromptBuilder(context=context)

        assert builder.context is context

    @pytest.mark.unit
    def test_uses_context_structure_for_project_type(self, temp_project_dir):
        """SystemPromptBuilder should use context.structure for project type detection."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create Python project
        (temp_project_dir / 'requirements.txt').write_text('flask==2.0.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)

        # Should use context's detection
        assert context.structure.get('has_requirements') is True
        assert builder.project_type == 'python'



class TestPromptBuilderPlatformAwareness:
    """SystemPromptBuilder should provide platform-specific guidance only."""

    @pytest.mark.unit
    @patch.object(CodebaseContext, 'get_platform', return_value='windows')
    def test_windows_prompt_includes_cmd_commands(self, mock_platform, temp_project_dir):
        """Windows prompt should include cmd.exe commands, not Unix."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should include Windows commands
        assert 'mkdir' in prompt
        assert 'copy' in prompt or 'xcopy' in prompt

        # Should NOT include Unix-specific commands
        assert 'mkdir -p' not in prompt
        assert 'cp -r' not in prompt

    @pytest.mark.unit
    @patch.object(CodebaseContext, 'get_platform', return_value='unix')
    def test_unix_prompt_includes_unix_commands(self, mock_platform, temp_project_dir):
        """Unix prompt should include Unix commands, not Windows."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should include Unix commands
        assert 'mkdir -p' in prompt or 'mkdir' in prompt
        assert 'cp' in prompt

        # Should NOT include Windows-specific commands
        assert 'xcopy' not in prompt
        assert 'cmd.exe' not in prompt

    @pytest.mark.unit
    @patch.object(CodebaseContext, 'get_platform', return_value='windows')
    def test_windows_prompt_warns_about_powershell(self, mock_platform, temp_project_dir):
        """Windows prompt should warn against PowerShell cmdlets."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should explicitly warn about PowerShell
        assert 'PowerShell' in prompt or 'powershell' in prompt
        assert 'New-Item' in prompt or 'cmdlet' in prompt

    @pytest.mark.unit
    def test_platform_auto_detected(self, temp_project_dir):
        """Platform should be auto-detected from system."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        import sys

        builder = SystemPromptBuilder(project_root=temp_project_dir)

        # Should detect current platform
        if sys.platform == 'win32':
            assert builder.platform == 'windows'
        else:
            assert builder.platform in ('unix', 'darwin', 'linux')


class TestPromptBuilderProjectTypeAwareness:
    """SystemPromptBuilder should tailor guidance to project type from context."""

    @pytest.mark.unit
    def test_python_project_gets_python_guidance(self, temp_project_dir):
        """Python projects should get Python-specific guidance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create a Python project marker
        (temp_project_dir / 'requirements.txt').write_text('flask==2.0.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should include Python guidance
        assert 'requirements.txt' in prompt or 'pip' in prompt or 'python' in prompt.lower()

        # Should NOT include irrelevant framework examples
        assert 'pom.xml' not in prompt
        assert 'Spring Boot' not in prompt
        assert 'package.json' not in prompt or 'Node' not in prompt

    @pytest.mark.unit
    def test_java_project_gets_java_guidance(self, tmp_path):
        """Java/Maven projects should get Java-specific guidance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create a Java project marker (use tmp_path to avoid pyproject.toml)
        (tmp_path / 'pom.xml').write_text('<project></project>\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should include Java guidance
        assert 'pom.xml' in prompt or 'maven' in prompt.lower() or 'java' in prompt.lower()

        # Should NOT include irrelevant guidance
        assert 'requirements.txt' not in prompt
        assert 'package.json' not in prompt or 'npm' not in prompt

    @pytest.mark.unit
    def test_nodejs_project_gets_node_guidance(self, tmp_path):
        """Node.js projects should get Node-specific guidance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create a Node project marker (use tmp_path to avoid pyproject.toml)
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should include Node guidance
        assert 'package.json' in prompt or 'npm' in prompt or 'node' in prompt.lower()

        # Should NOT include irrelevant guidance
        assert 'pom.xml' not in prompt
        assert 'requirements.txt' not in prompt

    @pytest.mark.unit
    def test_unknown_project_gets_generic_guidance(self, temp_project_dir):
        """Projects without markers should get generic guidance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should have basic guidance but not framework-specific
        assert 'read_file' in prompt or 'write_file' in prompt
        # Should not have specific framework examples
        assert 'Spring Boot' not in prompt
        assert 'React' not in prompt
        assert 'Flask' not in prompt


class TestPromptBuilderSuccinctness:
    """SystemPromptBuilder should produce concise prompts."""

    @pytest.mark.unit
    @patch.object(CodebaseContext, 'get_platform', return_value='windows')
    def test_prompt_does_not_include_all_platform_examples(self, mock_platform, temp_project_dir):
        """Prompt should not include examples for ALL platforms."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should not have Unix examples on Windows
        assert 'chmod +x' not in prompt
        assert 'brew install' not in prompt

    @pytest.mark.unit
    def test_prompt_does_not_include_all_framework_examples(self, temp_project_dir):
        """Prompt should not include examples for ALL frameworks."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Python project
        (temp_project_dir / 'requirements.txt').write_text('django==4.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Count framework mentions - should be focused
        spring_count = prompt.lower().count('spring')
        react_count = prompt.lower().count('react')
        vite_count = prompt.lower().count('vite')

        # Should not have extensive examples of irrelevant frameworks
        assert spring_count == 0, f"Spring mentioned {spring_count} times in Python project"
        assert react_count == 0 or react_count <= 1  # Maybe one generic mention is OK
        assert vite_count == 0

    @pytest.mark.unit
    def test_prompt_length_is_reasonable(self, temp_project_dir):
        """Prompt should not be excessively long."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Current prompt is ~2000 characters. New one should be similar or smaller
        # when only relevant sections are included
        assert len(prompt) < 5000, f"Prompt too long: {len(prompt)} characters"

        # Should be at least substantial enough to be useful
        assert len(prompt) > 500, f"Prompt too short: {len(prompt)} characters"


class TestPromptBuilderContextCaching:
    """SystemPromptBuilder should leverage context's caching."""

    @pytest.mark.unit
    def test_multiple_builds_use_same_context(self, temp_project_dir):
        """Multiple build() calls should reuse the same context."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = SystemPromptBuilder(context=context)

        prompt1 = builder.build()
        prompt2 = builder.build()

        # Should produce identical results
        assert prompt1 == prompt2

    @pytest.mark.unit
    def test_context_explored_once_on_first_build(self, temp_project_dir):
        """Context should be explored once when first needed."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = SystemPromptBuilder(context=context)

        # Context not explored yet
        assert not context.is_explored()

        # First build should trigger exploration
        _ = builder.build()
        assert context.is_explored()

        # Second build should not re-explore
        with patch.object(context, 'explore', wraps=context.explore) as mock_explore:
            _ = builder.build()
            mock_explore.assert_not_called()


class TestPromptBuilderAccuracy:
    """SystemPromptBuilder should provide accurate, actionable guidance."""

    @pytest.mark.unit
    @patch.object(CodebaseContext, 'get_platform', return_value='windows')
    def test_windows_provides_correct_mkdir_syntax(self, mock_platform, temp_project_dir):
        """Windows prompt should show correct mkdir syntax."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should provide correct Windows syntax
        # Either show 'mkdir' without -p, or explain Windows doesn't need -p
        if 'mkdir' in prompt:
            # Should not suggest mkdir -p on Windows (cmd.exe mkdir creates parents by default)
            assert 'mkdir -p' not in prompt

    @pytest.mark.unit
    def test_prompt_includes_tool_names(self, temp_project_dir):
        """Prompt should reference actual available tools."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should mention real tool names
        core_tools = ['read_file', 'write_file', 'run_command', 'list_files', 'search_code']
        tools_mentioned = sum(1 for tool in core_tools if tool in prompt)

        # At least some core tools should be mentioned
        assert tools_mentioned >= 3, f"Only {tools_mentioned} core tools mentioned in prompt"

    @pytest.mark.unit
    def test_prompt_includes_json_format_requirement(self, temp_project_dir):
        """Prompt should specify JSON response format."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Must specify JSON format (critical for parsing)
        assert 'JSON' in prompt or 'json' in prompt
        # Should mention true/false not True/False
        assert 'true/false' in prompt or 'lowercase' in prompt


class TestPromptBuilderComposability:
    """PromptBuilder sections should be composable."""

    @pytest.mark.unit
    def test_can_add_custom_section(self, temp_project_dir):
        """Should be able to add custom guidance sections."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        builder.add_section('security', 'Never commit secrets to version control.')

        prompt = builder.build()
        assert 'Never commit secrets' in prompt

    @pytest.mark.unit
    def test_can_override_section(self, temp_project_dir):
        """Should be able to override default sections."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        builder.set_section('platform', 'Custom platform guidance here.')

        prompt = builder.build()
        assert 'Custom platform guidance' in prompt

    @pytest.mark.unit
    def test_task_context_included(self, temp_project_dir):
        """Task description should be included in prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build(task="Fix the authentication bug in login.py")

        assert 'Fix the authentication bug' in prompt or 'login.py' in prompt


class TestCodebaseContextJavaSupport:
    """CodebaseContext should detect Java/Maven projects."""

    @pytest.mark.unit
    def test_context_detects_pom_xml(self, temp_project_dir):
        """CodebaseContext should detect pom.xml for Maven projects."""
        (temp_project_dir / 'pom.xml').write_text('<project></project>\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        # This test will fail until we add has_pom_xml to CodebaseContext
        assert context.structure.get('has_pom_xml') is True

    @pytest.mark.unit
    def test_context_detects_build_gradle(self, temp_project_dir):
        """CodebaseContext should detect build.gradle for Gradle projects."""
        (temp_project_dir / 'build.gradle').write_text('plugins { id "java" }\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        # This test will fail until we add has_build_gradle to CodebaseContext
        assert context.structure.get('has_build_gradle') is True


class TestPromptBuilderToolRegistryIntegration:
    """SystemPromptBuilder should integrate with ToolRegistry for tool descriptions."""

    @pytest.mark.unit
    def test_accepts_tool_registry(self, temp_project_dir):
        """SystemPromptBuilder should accept a ToolRegistry instance."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(project_root=temp_project_dir, tool_registry=registry)

        assert builder.tool_registry is registry

    @pytest.mark.unit
    def test_uses_registry_descriptions_in_prompt(self, temp_project_dir):
        """Tool descriptions should come from registry, not hardcoded."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry, ReadFileTool

        registry = ToolRegistry()
        registry.register(ReadFileTool())

        builder = SystemPromptBuilder(project_root=temp_project_dir, tool_registry=registry)
        prompt = builder.build()

        # Should include the actual tool description from registry
        assert 'read_file' in prompt
        # Should have the parameter info from the tool itself (ReadFileTool uses 'path')
        assert 'path' in prompt

    @pytest.mark.unit
    def test_uses_registry_response_format(self, temp_project_dir):
        """Response format should come from registry, not generic builder."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(project_root=temp_project_dir, tool_registry=registry)
        prompt = builder.build()

        # Should include registry's response format (thought/action/parameters/is_complete)
        assert '"thought"' in prompt
        assert '"action"' in prompt
        assert '"parameters"' in prompt
        assert '"is_complete"' in prompt

        # Should NOT have the old generic format with "reasoning"
        assert '"reasoning"' not in prompt

    @pytest.mark.unit
    def test_includes_complete_action_example(self, temp_project_dir):
        """Should show how to mark task as complete."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(project_root=temp_project_dir, tool_registry=registry)
        prompt = builder.build()

        # Should show completion format
        assert '"action": "complete"' in prompt or 'action.*complete' in prompt
        assert 'is_complete": true' in prompt or 'is_complete.*true' in prompt

    @pytest.mark.unit
    def test_tool_registry_overrides_default_tools_section(self, temp_project_dir):
        """When registry provided, it should replace default tools section entirely."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry, GitLogTool

        # Registry with only git tool
        registry = ToolRegistry()
        registry.register(GitLogTool())

        builder = SystemPromptBuilder(project_root=temp_project_dir, tool_registry=registry)
        prompt = builder.build()

        # Should only have tools from registry
        assert 'git_log' in prompt
        # Should NOT have the generic tools section listing
        # (the one that lists read_file, write_file etc generically)
        # The exact tool list should come from the registry
        assert 'list_files' not in prompt  # Not in this registry


class TestPromptBuilderStrategyGuidance:
    """SystemPromptBuilder should have strategy guidance as a proper section."""


    @pytest.mark.unit
    def test_strategy_section_prefers_write_file(self, temp_project_dir):
        """Strategy section should recommend write_file over scaffolding."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_strategy_section()

        # Should recommend write_file
        assert 'write_file' in section.lower()
        # Should discourage scaffolding
        assert 'scaffold' in section.lower() or 'curl' in section.lower()

    @pytest.mark.unit
    def test_strategy_section_included_in_build(self, temp_project_dir):
        """Strategy guidance should be in the final prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should have strategy guidance integrated
        assert 'write_file' in prompt
        # Should mention the prefer write_file approach
        assert 'prefer' in prompt.lower() or 'recommend' in prompt.lower()


class TestPromptBuilderEfficiencyRules:
    """SystemPromptBuilder should have efficiency rules as a proper section."""


    @pytest.mark.unit
    def test_efficiency_section_mentions_skip_redundant(self, temp_project_dir):
        """Efficiency section should mention skipping redundant operations."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_efficiency_section()

        # Should mention avoiding redundant operations
        assert 'redundant' in section.lower() or 'skip' in section.lower()
        # Should mention reusing information
        assert 'reuse' in section.lower() or 'already' in section.lower()

    @pytest.mark.unit
    def test_efficiency_section_mentions_no_repeat_reads(self, temp_project_dir):
        """Efficiency section should warn against re-reading files."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_efficiency_section()

        # Should mention not re-reading files
        assert 'read' in section.lower()
        # Should mention context or previous results
        assert 'previous' in section.lower() or 'already' in section.lower()

    @pytest.mark.unit
    def test_efficiency_rules_in_final_prompt(self, temp_project_dir):
        """Efficiency rules should appear in the final prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should have efficiency guidance
        assert 'redundant' in prompt.lower() or 'skip' in prompt.lower()


class TestPromptBuilderCompletionSemantics:
    """SystemPromptBuilder should have completion semantics as a proper section."""


    @pytest.mark.unit
    def test_completion_section_defines_when_done(self, temp_project_dir):
        """Completion section should define when to mark task complete."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_completion_section()

        # Should mention when to complete
        assert 'complete' in section.lower()
        # Should mention primary goal or deliverable
        assert 'primary' in section.lower() or 'goal' in section.lower() or 'done' in section.lower()

    @pytest.mark.unit
    def test_completion_section_warns_against_extras(self, temp_project_dir):
        """Completion section should warn against adding unrequested extras."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_completion_section()

        # Should mention not adding extras
        assert 'optional' in section.lower() or 'extra' in section.lower() or 'unless' in section.lower()

    @pytest.mark.unit
    def test_completion_semantics_in_final_prompt(self, temp_project_dir):
        """Completion semantics should appear in the final prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should have completion guidance
        assert 'is_complete' in prompt


class TestPromptBuilderSafetyRules:
    """SystemPromptBuilder should have safety rules as a proper section."""


    @pytest.mark.unit
    def test_safety_section_warns_empty_files(self, temp_project_dir):
        """Safety section should warn against empty file writes."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_safety_section()

        # Should warn about empty files
        assert 'empty' in section.lower()
        assert 'write' in section.lower() or 'content' in section.lower()

    @pytest.mark.unit
    def test_safety_section_enforces_json_format(self, temp_project_dir):
        """Safety section should enforce JSON format rules."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_safety_section()

        # Should mention JSON format
        assert 'json' in section.lower() or 'JSON' in section
        # Should mention true/false (not True/False)
        assert 'true' in section.lower() and 'false' in section.lower()

    @pytest.mark.unit
    def test_safety_section_mentions_incremental_changes(self, temp_project_dir):
        """Safety section should recommend incremental changes."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        section = builder._build_safety_section()

        # Should mention incremental or careful changes
        assert 'incremental' in section.lower() or 'careful' in section.lower() or 'small' in section.lower()

    @pytest.mark.unit
    def test_safety_rules_in_final_prompt(self, temp_project_dir):
        """Safety rules should appear in the final prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should have safety guidance about JSON
        assert 'true/false' in prompt or 'lowercase' in prompt


class TestPromptBuilderCodeAgentIntegration:
    """SystemPromptBuilder should integrate cleanly with CodeAgent."""

    @pytest.mark.unit
    def test_code_agent_uses_prompt_builder_registry(self, temp_project_dir):
        """CodeAgent should pass its tool registry to PromptBuilder."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        # This tests that the PromptBuilder can accept and use the registry
        # that CodeAgent would provide
        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        prompt = builder.build()

        # All tools from registry should be in prompt
        for tool_name in registry.list_tools():
            assert tool_name in prompt, f"Tool {tool_name} not in prompt"

    @pytest.mark.unit
    def test_prompt_builder_produces_complete_agent_prompt(self, temp_project_dir):
        """PromptBuilder.build() should produce a complete prompt without needing add_section."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        # No add_section calls needed - build() should include everything
        prompt = builder.build(task="Fix the login bug")

        # Should have all necessary sections built-in
        required_content = [
            'thought',           # Response format
            'action',            # Response format
            'is_complete',       # Completion semantics
            'write_file',        # Strategy (prefer write_file)
            'JSON',              # Safety rules
            'Fix the login bug', # Task context
        ]

        for content in required_content:
            assert content in prompt, f"Missing '{content}' in prompt"

    @pytest.mark.unit
    def test_no_duplicate_json_format_instructions(self, temp_project_dir):
        """Prompt should not have duplicate JSON format instructions."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        prompt = builder.build()

        # Should only have one set of response format instructions
        # Count occurrences of the format definition
        format_count = prompt.count('"thought":')
        # Should appear in the format example, maybe twice (tool call + complete)
        # but not more (would indicate duplication)
        assert format_count <= 3, f"JSON format appears {format_count} times (too many duplicates)"

    @pytest.mark.unit
    def test_sections_are_logically_ordered(self, temp_project_dir):
        """Prompt sections should follow logical order."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        prompt = builder.build(task="Test task")

        # Core identity should come first
        # Tools should come before response format
        tools_pos = prompt.find('read_file')
        format_pos = prompt.find('"thought"')

        # Strategy/efficiency should come after tools
        # Task should come last
        task_pos = prompt.find('Test task')

        # Verify ordering (allow some flexibility)
        assert tools_pos < task_pos, "Tools section should come before task"
        assert format_pos < task_pos, "Response format should come before task"


class TestPromptBuilderNoOperationalGuidanceBlob:
    """SystemPromptBuilder should NOT require a huge operational guidance blob."""

    @pytest.mark.unit
    def test_build_does_not_need_custom_operational_section(self, temp_project_dir):
        """PromptBuilder.build() should include operational concerns without add_section."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        # Build WITHOUT adding custom sections
        prompt = builder.build()

        # Should still have all operational guidance built-in
        assert 'write_file' in prompt  # Strategy
        assert 'redundant' in prompt.lower() or 'skip' in prompt.lower()  # Efficiency
        assert 'complete' in prompt.lower()  # Completion
        assert 'true/false' in prompt or 'lowercase' in prompt  # Safety

    @pytest.mark.unit
    def test_prompt_length_remains_reasonable_with_all_sections(self, temp_project_dir):
        """Full prompt with all sections should still be reasonable length."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(
            project_root=temp_project_dir,
            tool_registry=registry
        )

        prompt = builder.build(task="Complex multi-step task")

        # Should be comprehensive but not bloated
        # Current operational_guidance alone is ~2000 chars
        # With proper sections, total should be < 4000
        assert len(prompt) < 6000, f"Prompt too long: {len(prompt)} chars"
        assert len(prompt) > 1000, f"Prompt too short: {len(prompt)} chars"

    @pytest.mark.unit
    def test_each_section_is_focused(self, temp_project_dir):
        """Each section method should return focused, concise content."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        builder = SystemPromptBuilder(project_root=temp_project_dir)

        # Each section should be reasonable size
        sections_to_check = [
            ('_build_strategy_section', 300),    # Strategy shouldn't be > 300 chars
            ('_build_efficiency_section', 300),  # Efficiency shouldn't be > 300 chars
            ('_build_completion_section', 300),  # Completion shouldn't be > 300 chars
            ('_build_safety_section', 400),      # Safety can be slightly longer
        ]

        for method_name, max_length in sections_to_check:
            if hasattr(builder, method_name):
                section = getattr(builder, method_name)()
                assert len(section) < max_length, f"{method_name} too long: {len(section)} chars"
                assert len(section) > 50, f"{method_name} too short: {len(section)} chars"


class TestSystemPromptBuilderCodebaseStructure:
    """SystemPromptBuilder should include actual file locations from context."""

    @pytest.mark.unit
    def test_includes_javascript_file_locations(self, temp_project_dir):
        """Should show where JavaScript files are located."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create a frontend structure
        frontend_src = temp_project_dir / 'frontend' / 'src'
        frontend_src.mkdir(parents=True)
        (frontend_src / 'App.js').write_text('export default function App() {}')
        (frontend_src / 'index.js').write_text('import App from "./App"')
        (frontend_src / 'components').mkdir()
        (frontend_src / 'components' / 'LoginPage.js').write_text('export default function LoginPage() {}')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should include the actual paths
        assert 'frontend/src' in prompt or 'frontend\\src' in prompt
        # Should mention JavaScript files live there
        assert 'javascript' in prompt.lower() or 'js' in prompt.lower()

    @pytest.mark.unit
    def test_includes_python_file_locations(self, temp_project_dir):
        """Should show where Python files are located."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create src structure
        src_dir = temp_project_dir / 'src' / 'agent'
        src_dir.mkdir(parents=True)
        (src_dir / 'core.py').write_text('class Agent: pass')
        (src_dir / 'tools.py').write_text('def tool(): pass')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should include the actual paths
        assert 'src/agent' in prompt or 'src\\agent' in prompt
        # Should mention Python files
        assert 'python' in prompt.lower() or '.py' in prompt

    @pytest.mark.unit
    def test_shows_sub_project_locations(self, temp_project_dir):
        """Should show where different sub-projects are located."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create a monorepo structure
        # Python backend
        (temp_project_dir / 'requirements.txt').write_text('flask==2.0.0\n')

        # JavaScript frontend
        frontend = temp_project_dir / 'frontend'
        frontend.mkdir()
        (frontend / 'package.json').write_text('{"name": "frontend"}')
        frontend_src = frontend / 'src'
        frontend_src.mkdir()
        (frontend_src / 'App.js').write_text('export default function App() {}')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should indicate frontend is a sub-project
        assert 'frontend' in prompt.lower()

    @pytest.mark.unit
    def test_agent_knows_js_not_in_root(self, temp_project_dir):
        """Agent should know JavaScript files are NOT in root directory."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create JS files ONLY in frontend/src
        frontend_src = temp_project_dir / 'frontend' / 'src'
        frontend_src.mkdir(parents=True)
        (frontend_src / 'App.js').write_text('export default function App() {}')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        section = builder._build_codebase_structure_section()

        # Should indicate JS files are in frontend/src, not root
        # This is the key issue - agent needs to know WHERE to operate
        assert 'frontend' in section

    @pytest.mark.unit
    def test_empty_codebase_returns_minimal_section(self, temp_project_dir):
        """Empty codebase should return minimal/empty structure section."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        section = builder._build_codebase_structure_section()

        # Should be empty or minimal when no code files
        assert len(section) < 200 or section == ""

    @pytest.mark.unit
    def test_structure_section_included_in_build(self, temp_project_dir):
        """Codebase structure should be included in final prompt."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create some structure
        (temp_project_dir / 'src').mkdir(exist_ok=True)
        (temp_project_dir / 'src' / 'main.py').write_text('print("hello")')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        prompt = builder.build()

        # Should have codebase structure in the final prompt
        # Either as "Codebase Structure" section header or the actual paths
        assert 'src' in prompt

    @pytest.mark.unit
    def test_structure_section_concise(self, temp_project_dir):
        """Structure section should be concise, not dump entire file list."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create many files
        src_dir = temp_project_dir / 'src'
        src_dir.mkdir(exist_ok=True)
        for i in range(50):
            (src_dir / f'module_{i}.py').write_text(f'# module {i}')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        section = builder._build_codebase_structure_section()

        # Should summarize, not list all 50 files
        # Should be under 1000 characters
        assert len(section) < 1000, f"Structure section too verbose: {len(section)} chars"
        # Should show count or directory, not every file
        assert 'src' in section or 'python' in section.lower()

    @pytest.mark.unit
    def test_shows_directory_not_file_list(self, temp_project_dir):
        """Should show directories containing files, not individual file names."""
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create nested structure
        frontend_src = temp_project_dir / 'frontend' / 'src' / 'components'
        frontend_src.mkdir(parents=True)
        (frontend_src / 'Button.js').write_text('export default Button')
        (frontend_src / 'Input.js').write_text('export default Input')
        (frontend_src / 'Form.js').write_text('export default Form')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = SystemPromptBuilder(context=context)
        section = builder._build_codebase_structure_section()

        # Should show directory path
        assert 'frontend' in section
        # Should NOT list every component file
        assert section.count('.js') <= 3  # Maybe a couple examples, not all

    @pytest.mark.unit
    def test_prompt_length_reasonable_with_structure(self, temp_project_dir):
        """Prompt should remain reasonable length even with structure section."""
        from src.agent.system_prompt_builder import SystemPromptBuilder
        from src.agent_tools.tools import ToolRegistry

        # Create realistic structure
        frontend_src = temp_project_dir / 'frontend' / 'src'
        frontend_src.mkdir(parents=True, exist_ok=True)
        for name in ['App.js', 'index.js', 'utils.js']:
            (frontend_src / name).write_text(f'// {name}')

        src_dir = temp_project_dir / 'src'
        src_dir.mkdir(exist_ok=True)
        for name in ['main.py', 'utils.py', 'config.py']:
            (src_dir / name).write_text(f'# {name}')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        registry = ToolRegistry.create_default()
        builder = SystemPromptBuilder(context=context, tool_registry=registry)
        prompt = builder.build()

        # Should still be reasonable
        assert len(prompt) < 8000, f"Prompt too long with structure: {len(prompt)} chars"
