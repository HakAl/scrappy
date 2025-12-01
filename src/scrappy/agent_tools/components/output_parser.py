"""
Output parsing and formatting component.

Implements OutputParserProtocol to parse, format, and detect
command output formats (JSON, YAML, text, errors).
"""

import json
from typing import Optional


class OutputParser:
    """
    Parses and formats command output with format detection.

    This class implements a single responsibility: output parsing and formatting.
    It does NOT execute commands or handle security validation.
    """

    def __init__(self):
        """Initialize output parser."""
        pass

    def parse(self, raw_output: str, max_length: int = 30000) -> str:
        """
        Parse and format raw command output.

        Handles truncation, format detection (JSON/YAML), and provides
        helpful guidance for common errors.

        Args:
            raw_output: Raw output from command execution
            max_length: Maximum output length before truncation

        Returns:
            Formatted output string
        """
        if not raw_output or raw_output == "(no output)":
            return raw_output

        # Truncate if necessary
        if len(raw_output) > max_length:
            raw_output = "... [truncated, showing last portion]\n" + raw_output[-max_length:]

        stripped = raw_output.strip()

        # Detect Spring Initializr errors
        if 'start.spring.io' in raw_output or 'spring' in raw_output.lower():
            error_indicators = [
                '400 bad request', '404 not found', '500 internal server error',
                'connection refused', 'unable to resolve', 'network error'
            ]
            output_lower = raw_output.lower()
            for error in error_indicators:
                if error in output_lower:
                    guidance = (
                        "\n\n[Spring Initializr Error Detected]\n"
                        "The Spring Initializr service returned an error. Common causes:\n"
                        "1. Invalid dependency names (use 'web' not 'spring-boot-starter-web')\n"
                        "2. Malformed URL parameters\n"
                        "3. Network connectivity issues\n\n"
                        "RECOMMENDED: Use write_file to create Spring Boot files directly:\n"
                        "- Create pom.xml with required dependencies\n"
                        "- Create main Application.java class\n"
                        "- Create application.properties\n"
                        "This is more reliable than downloading from Spring Initializr."
                    )
                    return raw_output + guidance

        # Try JSON detection
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                format_info = "[Auto-detected: JSON output]\n"
                if isinstance(parsed, dict):
                    format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                elif isinstance(parsed, list):
                    format_info += f"[Structure: Array with {len(parsed)} items]\n"
                return format_info + raw_output
            except json.JSONDecodeError:
                pass

        # Try YAML detection
        try:
            import yaml
            if ':' in stripped and not stripped.startswith('Error'):
                lines = stripped.split('\n')
                yaml_indicators = 0
                for line in lines[:10]:
                    if line.strip() and ':' in line:
                        if line.strip().endswith(':') or ': ' in line:
                            yaml_indicators += 1
                    if line.startswith('  ') or line.startswith('- '):
                        yaml_indicators += 1

                if yaml_indicators >= 3:
                    try:
                        parsed = yaml.safe_load(stripped)
                        if isinstance(parsed, (dict, list)):
                            format_info = "[Auto-detected: YAML output]\n"
                            if isinstance(parsed, dict):
                                format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                            elif isinstance(parsed, list):
                                format_info += f"[Structure: Array with {len(parsed)} items]\n"
                            return format_info + raw_output
                    except Exception:
                        pass
        except ImportError:
            pass

        return raw_output

    def detect_format(self, output: str) -> str:
        """
        Detect output format (json, yaml, text, error).

        Args:
            output: Command output to analyze

        Returns:
            Format type identifier: "json", "yaml", "text", or "error"
        """
        if not output:
            return "text"

        stripped = output.strip()

        # Check for errors
        if stripped.startswith('Error'):
            return "error"

        # Check for JSON
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                json.loads(stripped)
                return "json"
            except json.JSONDecodeError:
                pass

        # Check for YAML indicators
        if ':' in stripped:
            lines = stripped.split('\n')
            yaml_indicators = 0
            for line in lines[:10]:
                if line.strip() and ':' in line:
                    if line.strip().endswith(':') or ': ' in line:
                        yaml_indicators += 1
                if line.startswith('  ') or line.startswith('- '):
                    yaml_indicators += 1

            if yaml_indicators >= 3:
                try:
                    import yaml
                    parsed = yaml.safe_load(stripped)
                    if isinstance(parsed, (dict, list)):
                        return "yaml"
                except:
                    pass

        return "text"
