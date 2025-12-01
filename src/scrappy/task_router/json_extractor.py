"""
JSON extraction utility for parsing LLM responses.

Extracts JSON from various formats:
- Markdown code blocks (```json ... ```)
- Generic code blocks (``` ... ```)
- Plain text with JSON objects

Also provides:
- fix_json: Fix Python booleans/None and single quotes
- parse: Extract + fix + parse to dict in one step
"""

import json
import re
from typing import Any


class JSONExtractor:
    """
    Utility class for extracting JSON from LLM responses.

    LLM responses often contain JSON embedded in markdown code blocks
    or mixed with explanatory text. This extractor handles common patterns
    and applies priority-based extraction.

    Priority order:
    1. ```json code blocks (most explicit)
    2. ``` generic code blocks (likely structured output)
    3. Plain text JSON objects (fallback)

    Usage:
        extractor = JSONExtractor()
        json_str = extractor.extract(llm_response)
        data = json.loads(json_str)
    """

    def extract(self, text: str | None) -> str:
        """
        Extract JSON string from text response.

        Args:
            text: Raw text that may contain JSON in various formats

        Returns:
            Extracted JSON string, or empty string if no JSON found

        Examples:
            >>> extractor = JSONExtractor()
            >>> extractor.extract('```json\\n{"key": "value"}\\n```')
            '{"key": "value"}'

            >>> extractor.extract('Result: {"status": "ok"}')
            '{"status": "ok"}'
        """
        if text is None or text == "":
            return ""

        # Strip leading/trailing whitespace
        text = text.strip()

        if not text:
            return ""

        # Priority 1: Try ```json code blocks first
        if '```json' in text:
            extracted = self._extract_from_json_code_block(text)
            if extracted:
                return extracted

        # Priority 2: Try generic ``` code blocks
        if '```' in text:
            extracted = self._extract_from_generic_code_block(text)
            if extracted:
                return extracted

        # Priority 3: Try to find JSON object in plain text
        if '{' in text:
            extracted = self._extract_from_plain_text(text)
            if extracted:
                return extracted

        # No JSON found
        return ""

    def _extract_from_json_code_block(self, text: str) -> str:
        """
        Extract JSON from ```json code block.

        Args:
            text: Text containing ```json block

        Returns:
            Extracted JSON string or empty string
        """
        start_marker = '```json'
        end_marker = '```'

        start_idx = text.find(start_marker)
        if start_idx == -1:
            return ""

        # Move past the opening marker
        start_idx += len(start_marker)

        # Find closing marker after opening
        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1:
            # No closing marker - try to extract JSON anyway
            return self._extract_from_plain_text(text[start_idx:])

        # Extract content between markers
        content = text[start_idx:end_idx].strip()
        return content

    def _extract_from_generic_code_block(self, text: str) -> str:
        """
        Extract JSON from generic ``` code block.

        Args:
            text: Text containing ``` block

        Returns:
            Extracted JSON string or empty string
        """
        # Find first ``` that is NOT part of ```json
        start_idx = 0
        while True:
            start_idx = text.find('```', start_idx)
            if start_idx == -1:
                return ""

            # Check if this is ```json (skip it)
            if text[start_idx:start_idx+7] == '```json':
                start_idx += 7
                continue

            # Found a generic ```
            break

        # Move past the opening ```
        start_idx += 3

        # Find closing ```
        end_idx = text.find('```', start_idx)
        if end_idx == -1:
            # No closing marker - try to extract JSON anyway
            return self._extract_from_plain_text(text[start_idx:])

        # Extract content between markers
        content = text[start_idx:end_idx].strip()
        return content

    def _extract_from_plain_text(self, text: str) -> str:
        """
        Extract JSON object from plain text.

        Finds the first '{' and last '}' and extracts content between.
        This is a simple heuristic that works for most cases.

        Args:
            text: Plain text that may contain JSON

        Returns:
            Extracted JSON string or empty string
        """
        start_idx = text.find('{')
        if start_idx == -1:
            return ""

        end_idx = text.rfind('}')
        if end_idx == -1 or end_idx <= start_idx:
            return ""

        # Extract from first { to last }
        content = text[start_idx:end_idx + 1]
        return content

    def fix_json(self, text: str | None) -> str:
        """
        Fix common JSON issues from LLM output.

        Converts Python-style values to JSON-compliant values:
        - True -> true
        - False -> false
        - None -> null
        - Single quotes -> double quotes

        Args:
            text: JSON string with potential Python-style values

        Returns:
            Fixed JSON string, or empty string if input is None/empty

        Examples:
            >>> extractor = JSONExtractor()
            >>> extractor.fix_json('{"enabled": True}')
            '{"enabled": true}'

            >>> extractor.fix_json("{'key': 'value'}")
            '{"key": "value"}'
        """
        if text is None or text == "":
            return ""

        # Replace Python booleans with JSON booleans using word boundaries
        text = re.sub(r'\bTrue\b', 'true', text)
        text = re.sub(r'\bFalse\b', 'false', text)
        text = re.sub(r'\bNone\b', 'null', text)

        # Convert single quotes to double quotes
        text = text.replace("'", '"')

        return text

    def parse(self, text: str | None) -> dict[str, Any] | None:
        """
        Extract, fix, and parse JSON from text to a dictionary.

        Combines extract(), fix_json(), and json.loads() into one step.
        This is the recommended method for parsing LLM responses that
        may contain Python-style JSON.

        Args:
            text: Raw text that may contain JSON in various formats

        Returns:
            Parsed dictionary, or None if no valid JSON found

        Examples:
            >>> extractor = JSONExtractor()
            >>> extractor.parse('```json\\n{"enabled": True}\\n```')
            {'enabled': True}

            >>> extractor.parse('No JSON here')
            None
        """
        if text is None or text == "":
            return None

        # Extract JSON string from text
        json_str = self.extract(text)

        if not json_str:
            return None

        # Fix Python-style values
        json_str = self.fix_json(json_str)

        # Parse to dictionary
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
            # Handle arrays or other JSON types - wrap or return None
            return None
        except json.JSONDecodeError:
            return None
