"""
Tests for PromptBuilder - context-aware system prompt construction.

The PromptBuilder should:
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


class TestPromptBuilderUsesCodebaseContext:
    """PromptBuilder should leverage CodebaseContext for project detection."""

    @pytest.mark.unit
    def test_accepts_codebase_context_instance(self, temp_project_dir):
        """PromptBuilder should accept a CodebaseContext instance."""
        from src.agent.prompt_builder import PromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = PromptBuilder(context=context)

        assert builder.context is context

    @pytest.mark.unit
    def test_creates_context_if_not_provided(self, temp_project_dir):
        """PromptBuilder should create CodebaseContext if not provided."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)

        assert builder.context is not None
        assert isinstance(builder.context, CodebaseContext)

    @pytest.mark.unit
    def test_uses_context_structure_for_project_type(self, temp_project_dir):
        """PromptBuilder should use context.structure for project type detection."""
        from src.agent.prompt_builder import PromptBuilder

        # Create Python project
        (temp_project_dir / 'requirements.txt').write_text('flask==2.0.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = PromptBuilder(context=context)

        # Should use context's detection
        assert context.structure.get('has_requirements') is True
        assert builder.project_type == 'python'

    @pytest.mark.unit
    def test_does_not_duplicate_file_scanning(self, temp_project_dir):
        """PromptBuilder should not re-scan files if context already explored."""
        from src.agent.prompt_builder import PromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        # Track if explore is called again
        with patch.object(context, 'explore', wraps=context.explore) as mock_explore:
            builder = PromptBuilder(context=context)
            _ = builder.build()

            # Should not re-explore
            mock_explore.assert_not_called()


class TestPromptBuilderPlatformAwareness:
    """PromptBuilder should provide platform-specific guidance only."""

    @pytest.mark.unit
    @patch('src.agent.prompt_builder.is_windows', return_value=True)
    def test_windows_prompt_includes_cmd_commands(self, mock_is_win, temp_project_dir):
        """Windows prompt should include cmd.exe commands, not Unix."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should include Windows commands
        assert 'mkdir' in prompt
        assert 'copy' in prompt or 'xcopy' in prompt

        # Should NOT include Unix-specific commands
        assert 'mkdir -p' not in prompt
        assert 'cp -r' not in prompt

    @pytest.mark.unit
    @patch('src.agent.prompt_builder.is_windows', return_value=False)
    def test_unix_prompt_includes_unix_commands(self, mock_is_win, temp_project_dir):
        """Unix prompt should include Unix commands, not Windows."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should include Unix commands
        assert 'mkdir -p' in prompt or 'mkdir' in prompt
        assert 'cp' in prompt

        # Should NOT include Windows-specific commands
        assert 'xcopy' not in prompt
        assert 'cmd.exe' not in prompt

    @pytest.mark.unit
    @patch('src.agent.prompt_builder.is_windows', return_value=True)
    def test_windows_prompt_warns_about_powershell(self, mock_is_win, temp_project_dir):
        """Windows prompt should warn against PowerShell cmdlets."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should explicitly warn about PowerShell
        assert 'PowerShell' in prompt or 'powershell' in prompt
        assert 'New-Item' in prompt or 'cmdlet' in prompt

    @pytest.mark.unit
    def test_platform_auto_detected(self, temp_project_dir):
        """Platform should be auto-detected from system."""
        from src.agent.prompt_builder import PromptBuilder
        import sys

        builder = PromptBuilder(project_root=temp_project_dir)

        # Should detect current platform
        if sys.platform == 'win32':
            assert builder.platform == 'windows'
        else:
            assert builder.platform in ('unix', 'darwin', 'linux')


class TestPromptBuilderProjectTypeAwareness:
    """PromptBuilder should tailor guidance to project type from context."""

    @pytest.mark.unit
    def test_python_project_gets_python_guidance(self, temp_project_dir):
        """Python projects should get Python-specific guidance."""
        from src.agent.prompt_builder import PromptBuilder

        # Create a Python project marker
        (temp_project_dir / 'requirements.txt').write_text('flask==2.0.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = PromptBuilder(context=context)
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
        from src.agent.prompt_builder import PromptBuilder

        # Create a Java project marker (use tmp_path to avoid pyproject.toml)
        (tmp_path / 'pom.xml').write_text('<project></project>\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        builder = PromptBuilder(context=context)
        prompt = builder.build()

        # Should include Java guidance
        assert 'pom.xml' in prompt or 'maven' in prompt.lower() or 'java' in prompt.lower()

        # Should NOT include irrelevant guidance
        assert 'requirements.txt' not in prompt
        assert 'package.json' not in prompt or 'npm' not in prompt

    @pytest.mark.unit
    def test_nodejs_project_gets_node_guidance(self, tmp_path):
        """Node.js projects should get Node-specific guidance."""
        from src.agent.prompt_builder import PromptBuilder

        # Create a Node project marker (use tmp_path to avoid pyproject.toml)
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        builder = PromptBuilder(context=context)
        prompt = builder.build()

        # Should include Node guidance
        assert 'package.json' in prompt or 'npm' in prompt or 'node' in prompt.lower()

        # Should NOT include irrelevant guidance
        assert 'pom.xml' not in prompt
        assert 'requirements.txt' not in prompt

    @pytest.mark.unit
    def test_unknown_project_gets_generic_guidance(self, temp_project_dir):
        """Projects without markers should get generic guidance."""
        from src.agent.prompt_builder import PromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = PromptBuilder(context=context)
        prompt = builder.build()

        # Should have basic guidance but not framework-specific
        assert 'read_file' in prompt or 'write_file' in prompt
        # Should not have specific framework examples
        assert 'Spring Boot' not in prompt
        assert 'React' not in prompt
        assert 'Flask' not in prompt


class TestPromptBuilderSuccinctness:
    """PromptBuilder should produce concise prompts."""

    @pytest.mark.unit
    @patch('src.agent.prompt_builder.is_windows', return_value=True)
    def test_prompt_does_not_include_all_platform_examples(self, mock_is_win, temp_project_dir):
        """Prompt should not include examples for ALL platforms."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should not have Unix examples on Windows
        assert 'chmod +x' not in prompt
        assert 'brew install' not in prompt

    @pytest.mark.unit
    def test_prompt_does_not_include_all_framework_examples(self, temp_project_dir):
        """Prompt should not include examples for ALL frameworks."""
        from src.agent.prompt_builder import PromptBuilder

        # Python project
        (temp_project_dir / 'requirements.txt').write_text('django==4.0\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        builder = PromptBuilder(context=context)
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
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Current prompt is ~2000 characters. New one should be similar or smaller
        # when only relevant sections are included
        assert len(prompt) < 5000, f"Prompt too long: {len(prompt)} characters"

        # Should be at least substantial enough to be useful
        assert len(prompt) > 500, f"Prompt too short: {len(prompt)} characters"


class TestPromptBuilderContextCaching:
    """PromptBuilder should leverage context's caching."""

    @pytest.mark.unit
    def test_multiple_builds_use_same_context(self, temp_project_dir):
        """Multiple build() calls should reuse the same context."""
        from src.agent.prompt_builder import PromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = PromptBuilder(context=context)

        prompt1 = builder.build()
        prompt2 = builder.build()

        # Should produce identical results
        assert prompt1 == prompt2

    @pytest.mark.unit
    def test_context_explored_once_on_first_build(self, temp_project_dir):
        """Context should be explored once when first needed."""
        from src.agent.prompt_builder import PromptBuilder

        context = CodebaseContext(str(temp_project_dir))
        builder = PromptBuilder(context=context)

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
    """PromptBuilder should provide accurate, actionable guidance."""

    @pytest.mark.unit
    @patch('src.agent.prompt_builder.is_windows', return_value=True)
    def test_windows_provides_correct_mkdir_syntax(self, mock_is_win, temp_project_dir):
        """Windows prompt should show correct mkdir syntax."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should provide correct Windows syntax
        # Either show 'mkdir' without -p, or explain Windows doesn't need -p
        if 'mkdir' in prompt:
            # Should not suggest mkdir -p on Windows (cmd.exe mkdir creates parents by default)
            assert 'mkdir -p' not in prompt

    @pytest.mark.unit
    def test_prompt_includes_tool_names(self, temp_project_dir):
        """Prompt should reference actual available tools."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        prompt = builder.build()

        # Should mention real tool names
        core_tools = ['read_file', 'write_file', 'run_command', 'list_files', 'search_code']
        tools_mentioned = sum(1 for tool in core_tools if tool in prompt)

        # At least some core tools should be mentioned
        assert tools_mentioned >= 3, f"Only {tools_mentioned} core tools mentioned in prompt"

    @pytest.mark.unit
    def test_prompt_includes_json_format_requirement(self, temp_project_dir):
        """Prompt should specify JSON response format."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
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
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        builder.add_section('security', 'Never commit secrets to version control.')

        prompt = builder.build()
        assert 'Never commit secrets' in prompt

    @pytest.mark.unit
    def test_can_override_section(self, temp_project_dir):
        """Should be able to override default sections."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
        builder.set_section('platform', 'Custom platform guidance here.')

        prompt = builder.build()
        assert 'Custom platform guidance' in prompt

    @pytest.mark.unit
    def test_task_context_included(self, temp_project_dir):
        """Task description should be included in prompt."""
        from src.agent.prompt_builder import PromptBuilder

        builder = PromptBuilder(project_root=temp_project_dir)
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
