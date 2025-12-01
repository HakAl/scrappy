"""
Regex-based entity extractor.

Extracts structured entities (file paths, class names, etc.) from user queries.
"""

import re
from typing import Dict, List, Set, Optional
from ..protocols import EntityExtractorProtocol
from .patterns import ENTITY_PATTERNS, COMMON_WORDS


class RegexEntityExtractor(EntityExtractorProtocol):
    """
    Regex-based entity extractor.

    Extracts structured entities from queries using pattern matching.
    Filters out common English words to reduce false positives.

    Dependencies:
    - patterns: Dictionary mapping entity types to regex patterns
    - common_words: Set of common English words to filter out

    Example:
        extractor = RegexEntityExtractor()
        entities = extractor.extract("check src/main.py")
        assert 'file_path' in entities
        assert 'src/main.py' in entities['file_path']
    """

    def __init__(
        self,
        patterns: Optional[Dict[str, List[str]]] = None,
        common_words: Optional[Set[str]] = None,
    ):
        """
        Initialize extractor with patterns.

        Args:
            patterns: Optional custom patterns. Defaults to ENTITY_PATTERNS.
            common_words: Optional set of common words to filter. Defaults to COMMON_WORDS.
        """
        self.patterns = patterns if patterns is not None else ENTITY_PATTERNS
        self.common_words = common_words if common_words is not None else COMMON_WORDS

    def extract(self, query: str) -> Dict[str, List[str]]:
        """
        Extracts entities like filenames, classes, functions, etc.

        Applies pattern matching for each entity type, then filters
        and deduplicates results.

        Args:
            query: User's query string

        Returns:
            Dictionary mapping entity types to lists of extracted values.
            Only includes entity types with at least one match.
        """
        if not query:
            return {}

        entities: Dict[str, Set[str]] = {key: set() for key in self.patterns}

        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    for match in matches:
                        if isinstance(match, tuple):
                            entities[entity_type].update(m for m in match if m)
                        else:
                            entities[entity_type].add(match)

        self._filter_class_names(entities)
        self._filter_function_names(entities)

        return {k: list(v) for k, v in entities.items() if v}

    def _filter_class_names(self, entities: Dict[str, Set[str]]) -> None:
        """
        Filter class names to remove common words and false positives.

        Keeps only names that:
        - Are not common English words
        - Are longer than 2 characters
        - Have multiple capitals (PascalCase) or specific suffixes

        Args:
            entities: Dictionary of entity sets (modified in place)
        """
        if 'class_name' not in entities:
            return

        class_suffixes = (
            'Error', 'Exception', 'Handler', 'Manager', 'Service',
            'Repository', 'Controller', 'Factory', 'Builder', 'Provider',
            'Adapter', 'Interface', 'Base', 'Abstract', 'Client', 'Server',
            'Config', 'Settings', 'Model', 'View', 'Agent', 'Worker'
        )

        entities['class_name'] = {
            name for name in entities['class_name']
            if name.lower() not in self.common_words
            and len(name) > 2
            and (
                sum(1 for c in name if c.isupper()) > 1
                or name.endswith(class_suffixes)
            )
        }

    def _filter_function_names(self, entities: Dict[str, Set[str]]) -> None:
        """
        Filter function names to remove common words and false positives.

        Keeps only names that:
        - Are not common English words
        - Are longer than 2 characters

        Args:
            entities: Dictionary of entity sets (modified in place)
        """
        if 'function_name' not in entities:
            return

        entities['function_name'] = {
            name for name in entities['function_name']
            if name.lower() not in self.common_words and len(name) > 2
        }
