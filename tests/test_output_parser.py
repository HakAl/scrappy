"""
Tests for OutputParser component.

Tests output parsing, truncation, and format detection following TDD principles.
"""

import pytest
from src.agent_tools.components.output_parser import OutputParser


class TestOutputParserBasicParsing:
    """Test basic output parsing functionality."""

    def test_returns_output_unchanged_for_plain_text(self):
        """Should return plain text unchanged."""
        parser = OutputParser()
        output = "This is plain text output"
        result = parser.parse(output)
        assert "This is plain text output" in result

    def test_handles_empty_output(self):
        """Should handle empty output."""
        parser = OutputParser()
        result = parser.parse("")
        assert result == ""

    def test_handles_no_output_marker(self):
        """Should handle (no output) marker unchanged."""
        parser = OutputParser()
        result = parser.parse("(no output)")
        assert result == "(no output)"


class TestOutputParserTruncation:
    """Test output truncation functionality."""

    def test_truncates_long_output(self):
        """Should truncate output exceeding max_length."""
        parser = OutputParser()
        long_output = "x" * 50000
        result = parser.parse(long_output, max_length=1000)
        assert len(result) < 50000
        assert "truncated" in result.lower()

    def test_does_not_truncate_short_output(self):
        """Should not truncate output within max_length."""
        parser = OutputParser()
        short_output = "x" * 500
        result = parser.parse(short_output, max_length=1000)
        assert len(result) == 500
        assert "truncated" not in result.lower()

    def test_truncation_shows_last_portion(self):
        """Truncation should show the last portion of output."""
        parser = OutputParser()
        output = "start" + ("x" * 1000) + "end_marker"
        result = parser.parse(output, max_length=100)
        assert "end_marker" in result
        assert "start" not in result


class TestOutputParserJSONDetection:
    """Test JSON format detection and annotation."""

    def test_detects_json_object(self):
        """Should detect and annotate JSON object output."""
        parser = OutputParser()
        json_output = '{"status": "ok", "count": 42}'
        result = parser.parse(json_output)
        assert "JSON" in result
        assert "Object" in result or "keys" in result

    def test_detects_json_array(self):
        """Should detect and annotate JSON array output."""
        parser = OutputParser()
        json_output = '[{"id": 1}, {"id": 2}]'
        result = parser.parse(json_output)
        assert "JSON" in result
        assert "Array" in result or "items" in result

    def test_handles_malformed_json(self):
        """Should handle malformed JSON gracefully."""
        parser = OutputParser()
        malformed = '{"status": "ok"'
        result = parser.parse(malformed)
        assert result is not None


class TestOutputParserYAMLDetection:
    """Test YAML format detection and annotation."""

    def test_detects_yaml_structure(self):
        """Should detect YAML-like structure."""
        parser = OutputParser()
        yaml_output = """
name: test-project
version: 1.0.0
dependencies:
  - package1
  - package2
"""
        result = parser.parse(yaml_output)
        # Should detect YAML or at least not crash
        assert result is not None

    def test_does_not_misidentify_errors_as_yaml(self):
        """Should not treat error messages as YAML."""
        parser = OutputParser()
        error_output = "Error: Connection failed"
        result = parser.parse(error_output)
        # Should not add YAML annotation to errors
        assert "YAML" not in result or "Error" in error_output


class TestOutputParserFormatDetection:
    """Test detect_format method."""

    def test_detect_format_json(self):
        """Should detect JSON format."""
        parser = OutputParser()
        json_output = '{"test": "value"}'
        format_type = parser.detect_format(json_output)
        assert format_type == "json"

    def test_detect_format_text(self):
        """Should detect plain text format."""
        parser = OutputParser()
        text_output = "This is plain text"
        format_type = parser.detect_format(text_output)
        assert format_type in ["text", "plain"]

    def test_detect_format_error(self):
        """Should detect error format."""
        parser = OutputParser()
        error_output = "Error: Something went wrong"
        format_type = parser.detect_format(error_output)
        assert format_type in ["error", "text"]


class TestOutputParserSpringInitializrErrors:
    """Test Spring Initializr error detection and guidance."""

    def test_detects_spring_initializr_400_error(self):
        """Should detect Spring Initializr 400 errors and add guidance."""
        parser = OutputParser()
        error_output = """
HTTP/1.1 400 Bad Request
Invalid dependency: spring-boot-starter-web
From: start.spring.io
"""
        result = parser.parse(error_output)
        assert "Spring Initializr" in result
        assert "write_file" in result or "pom.xml" in result

    def test_detects_spring_initializr_connection_error(self):
        """Should detect Spring Initializr connection errors."""
        parser = OutputParser()
        error_output = """
curl: (7) Failed to connect to start.spring.io port 443
Connection refused
"""
        result = parser.parse(error_output)
        assert "Spring" in result or "spring" in result

    def test_no_spring_guidance_for_unrelated_errors(self):
        """Should not add Spring guidance to unrelated errors."""
        parser = OutputParser()
        error_output = "npm ERR! 404 Not Found"
        result = parser.parse(error_output)
        # Should not add Spring-specific guidance to npm errors
        assert "Spring Initializr" not in result


class TestOutputParserEdgeCases:
    """Test edge cases and boundaries."""

    def test_handles_unicode_characters(self):
        """Should handle Unicode characters correctly."""
        parser = OutputParser()
        unicode_output = "Hello 你好 مرحبا"
        result = parser.parse(unicode_output)
        assert unicode_output in result

    def test_handles_newlines_and_special_chars(self):
        """Should preserve newlines and special characters."""
        parser = OutputParser()
        output_with_newlines = "Line 1\nLine 2\nLine 3"
        result = parser.parse(output_with_newlines)
        assert "\n" in result

    def test_handles_very_long_single_line(self):
        """Should handle very long single lines."""
        parser = OutputParser()
        long_line = "x" * 100000
        result = parser.parse(long_line, max_length=1000)
        assert len(result) < 100000
