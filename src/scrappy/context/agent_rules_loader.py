"""
Agent rules loader for AGENTS.md and compatible files.

Discovers and loads agent instruction files following the emerging standard:
- AGENTS.md (preferred - 60k+ repos use this)
- CLAUDE.md (Claude Code compatibility)
- GEMINI.md (Gemini compatibility)
- .github/copilot-instructions.md (GitHub Copilot compatibility)
- .scrappy/rules/*.md (Scrappy-specific overrides)

Supports directory hierarchy where nearest file wins.

See: https://agents.md/
See: .docs/TODO/_WIP.md Phase 1
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, List, runtime_checkable
import logging

logger = logging.getLogger(__name__)


# Discovery order - first match wins
AGENT_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
]

# Additional rules directory
RULES_DIR = ".scrappy/rules"


@dataclass
class AgentRules:
    """
    Loaded agent rules with source information.

    Attributes:
        content: The rules content (markdown)
        source_file: Path to the file that was loaded
        additional_rules: Content from .scrappy/rules/*.md files
    """
    content: str
    source_file: Path
    additional_rules: List[tuple[Path, str]]  # [(path, content), ...]

    def get_combined_content(self) -> str:
        """
        Get all rules combined into a single string.

        Returns main rules followed by any additional .scrappy/rules/*.md content.
        """
        parts = [self.content]

        for path, content in self.additional_rules:
            parts.append(f"\n\n<!-- From {path.name} -->\n{content}")

        return "\n".join(parts)


@runtime_checkable
class AgentRulesLoaderProtocol(Protocol):
    """
    Protocol for loading agent rules files.

    Implementations:
    - AgentRulesLoader: Discovers and loads rules from filesystem
    - NullAgentRulesLoader: Returns None (no rules available)
    - MockAgentRulesLoader: Returns preset rules for testing
    """

    def load(self, working_dir: Optional[Path] = None) -> Optional[AgentRules]:
        """
        Load agent rules for the given directory.

        Searches for agent files in priority order, walking up the directory
        tree to find the nearest match.

        Args:
            working_dir: Directory to search from (defaults to cwd)

        Returns:
            AgentRules if found, None otherwise
        """
        ...

    def discover_file(self, working_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Discover which agent file would be loaded.

        Useful for debugging and testing without loading content.

        Args:
            working_dir: Directory to search from (defaults to cwd)

        Returns:
            Path to the agent file if found, None otherwise
        """
        ...


class AgentRulesLoader:
    """
    Loads agent rules from AGENTS.md and compatible files.

    Discovery order (first match wins):
    1. AGENTS.md - The emerging standard
    2. CLAUDE.md - Claude Code compatibility
    3. GEMINI.md - Gemini compatibility
    4. .github/copilot-instructions.md - GitHub Copilot compatibility

    Directory hierarchy: Searches from working_dir upward, nearest wins.

    Additional rules from .scrappy/rules/*.md are loaded as overrides.

    Example:
        loader = AgentRulesLoader()
        rules = loader.load(Path("/path/to/project"))
        if rules:
            print(f"Loaded from: {rules.source_file}")
            print(rules.get_combined_content())
    """

    def __init__(
        self,
        agent_files: Optional[List[str]] = None,
        rules_dir: str = RULES_DIR,
        max_depth: int = 10,
    ):
        """
        Initialize the loader.

        Args:
            agent_files: List of agent file names to search for (defaults to AGENT_FILES)
            rules_dir: Directory name for additional rules (defaults to .scrappy/rules)
            max_depth: Maximum directory depth to search upward
        """
        self._agent_files = agent_files or AGENT_FILES
        self._rules_dir = rules_dir
        self._max_depth = max_depth

    def load(self, working_dir: Optional[Path] = None) -> Optional[AgentRules]:
        """
        Load agent rules for the given directory.

        Args:
            working_dir: Directory to search from (defaults to cwd)

        Returns:
            AgentRules if found, None otherwise
        """
        if working_dir is None:
            working_dir = Path.cwd()

        working_dir = working_dir.resolve()

        # Find the main agent file
        agent_file = self._find_agent_file(working_dir)
        if agent_file is None:
            logger.debug("No agent rules file found in %s or parents", working_dir)
            return None

        # Load main content
        try:
            content = agent_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", agent_file, e)
            return None

        logger.info("Loaded agent rules from %s", agent_file)

        # Load additional rules from .scrappy/rules/
        additional = self._load_additional_rules(working_dir)

        return AgentRules(
            content=content,
            source_file=agent_file,
            additional_rules=additional,
        )

    def discover_file(self, working_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Discover which agent file would be loaded.

        Args:
            working_dir: Directory to search from (defaults to cwd)

        Returns:
            Path to the agent file if found, None otherwise
        """
        if working_dir is None:
            working_dir = Path.cwd()

        return self._find_agent_file(working_dir.resolve())

    def _find_agent_file(self, start_dir: Path) -> Optional[Path]:
        """
        Find the nearest agent file by walking up the directory tree.

        Args:
            start_dir: Directory to start searching from

        Returns:
            Path to agent file if found, None otherwise
        """
        current = start_dir
        depth = 0

        while depth < self._max_depth:
            # Check each agent file in priority order
            for filename in self._agent_files:
                candidate = current / filename
                if candidate.is_file():
                    return candidate

            # Move up one directory
            parent = current.parent
            if parent == current:
                # Reached root
                break

            current = parent
            depth += 1

        return None

    def _load_additional_rules(self, working_dir: Path) -> List[tuple[Path, str]]:
        """
        Load additional rules from .scrappy/rules/*.md.

        Args:
            working_dir: Project directory to search

        Returns:
            List of (path, content) tuples for each rules file found
        """
        rules_path = working_dir / self._rules_dir
        if not rules_path.is_dir():
            return []

        additional = []
        try:
            for md_file in sorted(rules_path.glob("*.md")):
                if md_file.is_file():
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        additional.append((md_file, content))
                        logger.debug("Loaded additional rules from %s", md_file)
                    except (OSError, UnicodeDecodeError) as e:
                        logger.warning("Failed to read %s: %s", md_file, e)
        except OSError as e:
            logger.warning("Failed to scan %s: %s", rules_path, e)

        return additional


class NullAgentRulesLoader:
    """
    No-op agent rules loader.

    Always returns None. Use when agent rules are not supported
    or explicitly disabled.
    """

    def load(self, working_dir: Optional[Path] = None) -> None:
        """Returns None - no rules available."""
        return None

    def discover_file(self, working_dir: Optional[Path] = None) -> None:
        """Returns None - no discovery."""
        return None


# Verify protocol compliance
def _verify_protocols() -> None:
    """Verify implementations satisfy the protocol."""
    assert isinstance(AgentRulesLoader(), AgentRulesLoaderProtocol)
    assert isinstance(NullAgentRulesLoader(), AgentRulesLoaderProtocol)


_verify_protocols()
