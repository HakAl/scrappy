"""Tests for agent rules loader (AGENTS.md support)."""

from pathlib import Path

from scrappy.context.agent_rules_loader import (
    AgentRulesLoader,
    AgentRules,
    NullAgentRulesLoader,
    AgentRulesLoaderProtocol,
    AGENT_FILES,
)


class TestAgentRulesLoader:
    """Tests for AgentRulesLoader."""

    def test_protocol_compliance(self):
        """Loader implements protocol."""
        loader = AgentRulesLoader()
        assert isinstance(loader, AgentRulesLoaderProtocol)

    def test_null_loader_protocol_compliance(self):
        """NullAgentRulesLoader implements protocol."""
        loader = NullAgentRulesLoader()
        assert isinstance(loader, AgentRulesLoaderProtocol)

    def test_load_agents_md(self, tmp_path: Path):
        """Loads AGENTS.md when present."""
        # Create AGENTS.md
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# Project Rules\n\nUse pytest for tests.\n")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert rules.source_file == agents_file
        assert "Use pytest for tests" in rules.content

    def test_load_claude_md_fallback(self, tmp_path: Path):
        """Falls back to CLAUDE.md when AGENTS.md not present."""
        # Create only CLAUDE.md
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("# Claude Rules\n\nBe helpful.\n")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert rules.source_file == claude_file
        assert "Be helpful" in rules.content

    def test_priority_order(self, tmp_path: Path):
        """AGENTS.md takes priority over CLAUDE.md."""
        # Create both files
        (tmp_path / "AGENTS.md").write_text("AGENTS content")
        (tmp_path / "CLAUDE.md").write_text("CLAUDE content")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert rules.source_file.name == "AGENTS.md"
        assert "AGENTS content" in rules.content

    def test_gemini_md_fallback(self, tmp_path: Path):
        """Falls back to GEMINI.md when others not present."""
        gemini_file = tmp_path / "GEMINI.md"
        gemini_file.write_text("Gemini rules")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert rules.source_file == gemini_file

    def test_copilot_instructions_fallback(self, tmp_path: Path):
        """Falls back to .github/copilot-instructions.md."""
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        copilot_file = github_dir / "copilot-instructions.md"
        copilot_file.write_text("Copilot rules")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert rules.source_file == copilot_file

    def test_no_rules_file(self, tmp_path: Path):
        """Returns None when no rules file found."""
        loader = AgentRulesLoader(max_depth=1)
        rules = loader.load(tmp_path)

        assert rules is None

    def test_directory_hierarchy_nearest_wins(self, tmp_path: Path):
        """Nearest AGENTS.md takes precedence over parent."""
        # Create parent AGENTS.md
        (tmp_path / "AGENTS.md").write_text("Parent rules")

        # Create child directory with its own AGENTS.md
        child_dir = tmp_path / "subproject"
        child_dir.mkdir()
        (child_dir / "AGENTS.md").write_text("Child rules")

        loader = AgentRulesLoader()

        # Loading from parent gets parent rules
        parent_rules = loader.load(tmp_path)
        assert parent_rules is not None
        assert "Parent rules" in parent_rules.content

        # Loading from child gets child rules
        child_rules = loader.load(child_dir)
        assert child_rules is not None
        assert "Child rules" in child_rules.content

    def test_walks_up_to_find_rules(self, tmp_path: Path):
        """Walks up directory tree to find rules file."""
        # Create AGENTS.md in root
        (tmp_path / "AGENTS.md").write_text("Root rules")

        # Create nested directory without rules
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)

        loader = AgentRulesLoader()
        rules = loader.load(nested)

        assert rules is not None
        assert "Root rules" in rules.content
        assert rules.source_file == tmp_path / "AGENTS.md"

    def test_additional_rules_from_scrappy_rules(self, tmp_path: Path):
        """Loads additional rules from .scrappy/rules/*.md."""
        # Create main AGENTS.md
        (tmp_path / "AGENTS.md").write_text("Main rules")

        # Create .scrappy/rules directory with additional files
        rules_dir = tmp_path / ".scrappy" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "python.md").write_text("Python specific rules")
        (rules_dir / "testing.md").write_text("Testing conventions")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert len(rules.additional_rules) == 2

        # Check combined content includes all rules
        combined = rules.get_combined_content()
        assert "Main rules" in combined
        assert "Python specific rules" in combined
        assert "Testing conventions" in combined

    def test_additional_rules_sorted_alphabetically(self, tmp_path: Path):
        """Additional rules are sorted alphabetically by filename."""
        (tmp_path / "AGENTS.md").write_text("Main")

        rules_dir = tmp_path / ".scrappy" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "z_last.md").write_text("Z content")
        (rules_dir / "a_first.md").write_text("A content")

        loader = AgentRulesLoader()
        rules = loader.load(tmp_path)

        assert rules is not None
        assert len(rules.additional_rules) == 2
        assert rules.additional_rules[0][0].name == "a_first.md"
        assert rules.additional_rules[1][0].name == "z_last.md"

    def test_discover_file(self, tmp_path: Path):
        """discover_file returns path without loading content."""
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("Content")

        loader = AgentRulesLoader()
        discovered = loader.discover_file(tmp_path)

        assert discovered == agents_file

    def test_discover_file_none_when_not_found(self, tmp_path: Path):
        """discover_file returns None when no file found."""
        loader = AgentRulesLoader(max_depth=1)
        discovered = loader.discover_file(tmp_path)

        assert discovered is None

    def test_max_depth_limit(self, tmp_path: Path):
        """Respects max_depth limit when walking up."""
        # Create AGENTS.md at root
        (tmp_path / "AGENTS.md").write_text("Root rules")

        # Create deeply nested directory (deeper than max_depth)
        deeply_nested = tmp_path
        for i in range(15):
            deeply_nested = deeply_nested / f"level{i}"
        deeply_nested.mkdir(parents=True)

        # With low max_depth, should not find the root file
        loader = AgentRulesLoader(max_depth=3)
        rules = loader.load(deeply_nested)

        assert rules is None

    def test_handles_read_errors_gracefully(self, tmp_path: Path):
        """Handles file read errors gracefully."""
        agents_file = tmp_path / "AGENTS.md"
        agents_file.mkdir()  # Create directory instead of file (will cause read error)

        loader = AgentRulesLoader(max_depth=1)
        rules = loader.load(tmp_path)

        # Should return None, not raise
        assert rules is None

    def test_null_loader_always_returns_none(self, tmp_path: Path):
        """NullAgentRulesLoader always returns None."""
        (tmp_path / "AGENTS.md").write_text("Rules")

        loader = NullAgentRulesLoader()
        assert loader.load(tmp_path) is None
        assert loader.discover_file(tmp_path) is None


class TestAgentRules:
    """Tests for AgentRules dataclass."""

    def test_get_combined_content_no_additional(self, tmp_path: Path):
        """Combined content with no additional rules returns main content."""
        rules = AgentRules(
            content="Main content",
            source_file=tmp_path / "AGENTS.md",
            additional_rules=[],
        )

        assert rules.get_combined_content() == "Main content"

    def test_get_combined_content_with_additional(self, tmp_path: Path):
        """Combined content includes additional rules with source comments."""
        rules = AgentRules(
            content="Main content",
            source_file=tmp_path / "AGENTS.md",
            additional_rules=[
                (tmp_path / ".scrappy" / "rules" / "extra.md", "Extra content"),
            ],
        )

        combined = rules.get_combined_content()
        assert "Main content" in combined
        assert "Extra content" in combined
        assert "extra.md" in combined  # Source file referenced


class TestAgentFilesConstant:
    """Tests for the AGENT_FILES constant."""

    def test_agents_md_first(self):
        """AGENTS.md is first in discovery order."""
        assert AGENT_FILES[0] == "AGENTS.md"

    def test_claude_md_second(self):
        """CLAUDE.md is second in discovery order."""
        assert AGENT_FILES[1] == "CLAUDE.md"

    def test_copilot_instructions_included(self):
        """Copilot instructions file is in the list."""
        assert ".github/copilot-instructions.md" in AGENT_FILES
