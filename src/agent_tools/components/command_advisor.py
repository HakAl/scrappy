"""
Command advisor component for framework-specific guidance.

Implements CommandAdvisorProtocol to provide pre-execution advice
and enrich error messages with contextual help.
"""

from typing import Optional


class CommandAdvisor:
    """
    Provides framework-specific command advice and error enrichment.

    This class implements a single responsibility: advisory and guidance.
    It does NOT execute commands or parse output.
    """

    def __init__(self):
        """Initialize command advisor."""
        pass

    def analyze_command(self, command: str) -> Optional[str]:
        """
        Analyze command and provide pre-execution advice.

        Args:
            command: Command to analyze

        Returns:
            Advisory message if applicable, None otherwise
        """
        cmd_lower = command.lower()

        # npm init without -y flag
        if 'npm init' in cmd_lower and '-y' not in cmd_lower:
            return "Consider using 'npm init -y' to skip interactive prompts"

        # npx without -y flag
        if 'npx' in cmd_lower and '-y' not in cmd_lower:
            return "Consider adding '-y' flag to npx to skip prompts: npx -y <package>"

        # yarn create
        if 'yarn create' in cmd_lower:
            return "yarn create may prompt for choices interactively"

        return None

    def enrich_output(self, output: str, command: str) -> str:
        """
        Enrich output with contextual information.

        Args:
            output: Raw command output
            command: Original command that was executed

        Returns:
            Enriched output with additional context
        """
        # Output is already enriched by OutputParser for Spring errors
        # This method can add command-specific context
        return output
