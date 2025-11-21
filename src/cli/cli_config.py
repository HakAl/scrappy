"""
Consolidated CLI configuration.

Brings together all CLI config modules (defaults, extensions, paths, patterns)
into a single, cohesive configuration class that extends BaseConfig.
"""

from dataclasses import dataclass, field
from typing import List, Set, Dict
import re

from src.infrastructure.config import BaseConfig

# Import from existing config modules
from src.cli.config.extensions import (
    PYTHON_EXTENSIONS,
    JAVASCRIPT_EXTENSIONS,
    WEB_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DOCS_EXTENSIONS,
    ALL_CODE_EXTENSIONS,
    ENTRY_POINT_FILES,
    PRIORITY_FILES,
    DEPENDENCY_FILES,
    CONFIGURATION_FILES,
)
from src.cli.config.paths import (
    SESSION_FILE,
    RATE_LIMITS_FILE,
    RESPONSE_CACHE_FILE,
    CONTEXT_FILE,
    AUDIT_FILE,
    SKIP_DIRS,
    SKIP_DIRS_MINIMAL,
    PROJECT_INDICATORS,
)
from src.cli.config.patterns import (
    WEB_PATTERNS,
    CODEBASE_PATTERNS,
    URL_PATTERN,
    PATH_PATTERN,
    PACKAGE_KEYWORDS,
    ACTION_KEYWORDS,
)


@dataclass
class CLIConfig(BaseConfig):
    """
    Consolidated CLI configuration.

    Centralizes all CLI configuration settings including:
    - Temperature and token limits
    - Line and content truncation
    - Display defaults
    - File extensions and categories
    - Path configuration
    - Pattern matching rules
    """

    # Temperature defaults for LLM responses
    temperature_low: float = 0.3
    temperature_default: float = 0.7

    # Token limit defaults
    max_tokens_query: int = 1000
    max_tokens_summary: int = 2000

    # Line limit defaults
    max_lines_config: int = 100
    max_lines_dependency: int = 50
    max_test_results: int = 20

    # Content truncation thresholds (ordered by size)
    truncate_error_message: int = 500
    truncate_research_medium: int = 1000
    truncate_research_large: int = 1500
    truncate_file_content: int = 2000
    truncate_priority_file: int = 3000

    # String preview length defaults
    preview_short: int = 40
    preview_standard: int = 50
    preview_conclusion: int = 200

    # Rate limit warning thresholds (as percentages)
    cache_hit_good: float = 0.50
    rate_limit_warning: float = 0.75
    rate_limit_critical: float = 0.90

    # Display defaults
    max_display_messages: int = 4
    progress_bar_width: int = 20
    dashboard_enabled: bool = True
    dashboard_refresh_rate: int = 4

    # Separator widths for console output
    separator_width_narrow: int = 40
    separator_width_standard: int = 50
    separator_width_wide: int = 60

    # Command defaults
    max_iterations: int = 10

    # File extensions
    python_extensions: List[str] = field(default_factory=lambda: PYTHON_EXTENSIONS.copy())
    javascript_extensions: List[str] = field(default_factory=lambda: JAVASCRIPT_EXTENSIONS.copy())
    web_extensions: List[str] = field(default_factory=lambda: WEB_EXTENSIONS.copy())
    config_extensions: List[str] = field(default_factory=lambda: CONFIG_EXTENSIONS.copy())
    docs_extensions: List[str] = field(default_factory=lambda: DOCS_EXTENSIONS.copy())
    all_code_extensions: List[str] = field(default_factory=lambda: ALL_CODE_EXTENSIONS.copy())

    # Important files
    entry_point_files: List[str] = field(default_factory=lambda: ENTRY_POINT_FILES.copy())
    priority_files: List[str] = field(default_factory=lambda: PRIORITY_FILES.copy())
    dependency_files: List[str] = field(default_factory=lambda: DEPENDENCY_FILES.copy())
    configuration_files: List[str] = field(default_factory=lambda: CONFIGURATION_FILES.copy())

    # Path configuration
    session_file: str = SESSION_FILE
    rate_limits_file: str = RATE_LIMITS_FILE
    response_cache_file: str = RESPONSE_CACHE_FILE
    context_file: str = CONTEXT_FILE
    audit_file: str = AUDIT_FILE

    skip_directories: Set[str] = field(default_factory=lambda: SKIP_DIRS.copy())
    skip_directories_minimal: Set[str] = field(default_factory=lambda: SKIP_DIRS_MINIMAL.copy())
    project_indicators: List[str] = field(default_factory=lambda: PROJECT_INDICATORS.copy())

    # Pattern configuration
    web_patterns: List[re.Pattern] = field(default_factory=lambda: WEB_PATTERNS.copy())
    codebase_patterns: List[re.Pattern] = field(default_factory=lambda: CODEBASE_PATTERNS.copy())
    url_pattern: re.Pattern = field(default_factory=lambda: URL_PATTERN)
    path_pattern: re.Pattern = field(default_factory=lambda: PATH_PATTERN)

    package_keywords: List[str] = field(default_factory=lambda: PACKAGE_KEYWORDS.copy())
    action_keywords: List[str] = field(default_factory=lambda: ACTION_KEYWORDS.copy())

    def validate(self) -> None:
        """
        Validate CLIConfig values.

        Raises:
            ValueError: If configuration is invalid
        """
        super().validate()

        # Validate temperature
        if not (0.0 <= self.temperature_low <= 2.0):
            raise ValueError(
                f"temperature_low must be between 0.0 and 2.0, got {self.temperature_low}"
            )

        if not (0.0 <= self.temperature_default <= 2.0):
            raise ValueError(
                f"temperature_default must be between 0.0 and 2.0, got {self.temperature_default}"
            )

        # Validate token limits
        if self.max_tokens_query <= 0:
            raise ValueError(
                f"max_tokens_query must be positive, got {self.max_tokens_query}"
            )

        if self.max_tokens_summary <= 0:
            raise ValueError(
                f"max_tokens_summary must be positive, got {self.max_tokens_summary}"
            )

        # Validate line limits
        if self.max_lines_config <= 0:
            raise ValueError(
                f"max_lines_config must be positive, got {self.max_lines_config}"
            )

        # Validate truncation thresholds
        if self.truncate_error_message <= 0:
            raise ValueError(
                f"truncate_error_message must be positive, got {self.truncate_error_message}"
            )

        # Validate percentages
        if not (0.0 <= self.cache_hit_good <= 1.0):
            raise ValueError(
                f"cache_hit_good must be between 0.0 and 1.0, got {self.cache_hit_good}"
            )

        if not (0.0 <= self.rate_limit_warning <= 1.0):
            raise ValueError(
                f"rate_limit_warning must be between 0.0 and 1.0, got {self.rate_limit_warning}"
            )

        if not (0.0 <= self.rate_limit_critical <= 1.0):
            raise ValueError(
                f"rate_limit_critical must be between 0.0 and 1.0, got {self.rate_limit_critical}"
            )

        # Validate display settings
        if self.max_display_messages <= 0:
            raise ValueError(
                f"max_display_messages must be positive, got {self.max_display_messages}"
            )

        if self.dashboard_refresh_rate <= 0:
            raise ValueError(
                f"dashboard_refresh_rate must be positive, got {self.dashboard_refresh_rate}"
            )

    def get_extensions_by_category(self) -> Dict[str, List[str]]:
        """
        Get file extensions organized by category.

        Returns:
            Dictionary mapping category names to extension lists
        """
        return {
            'python': self.python_extensions,
            'javascript': self.javascript_extensions,
            'web': self.web_extensions,
            'config': self.config_extensions,
            'docs': self.docs_extensions,
            'other': [],
        }

    def get_truncation_limits(self) -> Dict[str, int]:
        """
        Get truncation limits organized by type.

        Returns:
            Dictionary mapping truncation type to limit
        """
        return {
            'error_message': self.truncate_error_message,
            'research_medium': self.truncate_research_medium,
            'research_large': self.truncate_research_large,
            'file_content': self.truncate_file_content,
            'priority_file': self.truncate_priority_file,
        }

    def get_temperatures(self) -> Dict[str, float]:
        """
        Get temperature settings.

        Returns:
            Dictionary mapping temperature type to value
        """
        return {
            'low': self.temperature_low,
            'default': self.temperature_default,
        }

    def get_separator_widths(self) -> Dict[str, int]:
        """
        Get separator widths.

        Returns:
            Dictionary mapping separator type to width
        """
        return {
            'narrow': self.separator_width_narrow,
            'standard': self.separator_width_standard,
            'wide': self.separator_width_wide,
        }
