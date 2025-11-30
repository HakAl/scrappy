"""
Action resolver.

Maps intent classification results to executable actions.
"""

from typing import Dict, List
from ..protocols import (
    ActionResolverProtocol,
    IntentResult,
    QueryIntent,
    Action,
)


class DefaultActionResolver(ActionResolverProtocol):
    """
    Default action resolver.

    Maps intent classifications to concrete actions that can be executed
    by the system. Uses a straightforward mapping from intents to tools
    and functions.

    This follows the Open/Closed Principle: new intents can be added
    by extending the _intent_to_action method without modifying existing code.

    Example:
        resolver = DefaultActionResolver()
        result = IntentResult(QueryIntent.FILE_STRUCTURE, 0.8, {})
        entities = {'file_path': ['src/main.py']}
        action = resolver.resolve(result, entities)
        assert action.tool == 'FileSystem'
        assert action.func == 'list_directory'
    """

    def resolve(self, result: IntentResult, entities: Dict[str, List[str]]) -> Action:
        """
        Converts classification results into a concrete system action.

        Args:
            result: Intent classification result
            entities: Extracted entities from query

        Returns:
            Action object ready to be executed
        """
        return self._intent_to_action(result.intent, entities)

    def _intent_to_action(
        self,
        intent: QueryIntent,
        entities: Dict[str, List[str]],
    ) -> Action:
        """
        Map intent to action.

        Each intent maps to a specific tool/function combination.
        Entities are used to populate action arguments.

        Args:
            intent: Classified intent
            entities: Extracted entities

        Returns:
            Action to execute
        """
        if intent == QueryIntent.FILE_STRUCTURE:
            return self._file_structure_action(entities)

        elif intent == QueryIntent.CODE_EXPLANATION:
            return self._code_explanation_action(entities)

        elif intent == QueryIntent.GIT_HISTORY:
            return self._git_history_action(entities)

        elif intent == QueryIntent.DEPENDENCY_INFO:
            return self._dependency_info_action(entities)

        elif intent == QueryIntent.ARCHITECTURE:
            return self._architecture_action(entities)

        elif intent == QueryIntent.BUG_INVESTIGATION:
            return self._bug_investigation_action(entities)

        elif intent == QueryIntent.TESTING:
            return self._testing_action(entities)

        elif intent == QueryIntent.PERFORMANCE:
            return self._performance_action(entities)

        elif intent == QueryIntent.DOCUMENTATION:
            return self._documentation_action(entities)

        elif intent == QueryIntent.REFACTORING:
            return self._refactoring_action(entities)

        elif intent == QueryIntent.SECURITY:
            return self._security_action(entities)

        elif intent == QueryIntent.CONFIGURATION:
            return self._configuration_action(entities)

        else:
            return self._general_action(entities)

    def _file_structure_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for file structure queries."""
        path = entities.get('file_path', ['.'])[0] if entities.get('file_path') else '.'
        return Action(
            tool='FileSystem',
            func='list_directory',
            args={'path': path}
        )

    def _code_explanation_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for code explanation queries."""
        target = ''
        if entities.get('file_path'):
            target = entities['file_path'][0]
        elif entities.get('class_name'):
            target = entities['class_name'][0]
        elif entities.get('function_name'):
            target = entities['function_name'][0]

        return Action(
            tool='CodeExplainer',
            func='explain',
            args={'target': target, 'entities': entities}
        )

    def _git_history_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for git history queries."""
        file_path = entities.get('file_path', [''])[0] if entities.get('file_path') else ''
        return Action(
            tool='GitHistory',
            func='get_history',
            args={'file_path': file_path}
        )

    def _dependency_info_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for dependency info queries."""
        package = entities.get('package_name', [''])[0] if entities.get('package_name') else ''
        return Action(
            tool='DependencyAnalyzer',
            func='analyze',
            args={'package': package}
        )

    def _architecture_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for architecture queries."""
        return Action(
            tool='ArchitectureAnalyzer',
            func='analyze',
            args={'entities': entities}
        )

    def _bug_investigation_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for bug investigation queries."""
        error_type = entities.get('error_type', [''])[0] if entities.get('error_type') else ''
        return Action(
            tool='BugInvestigator',
            func='investigate',
            args={'error_type': error_type, 'entities': entities}
        )

    def _testing_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for testing queries."""
        target = entities.get('file_path', [''])[0] if entities.get('file_path') else ''
        return Action(
            tool='TestAnalyzer',
            func='analyze',
            args={'target': target}
        )

    def _performance_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for performance queries."""
        return Action(
            tool='PerformanceAnalyzer',
            func='analyze',
            args={'entities': entities}
        )

    def _documentation_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for documentation queries."""
        return Action(
            tool='DocumentationFinder',
            func='find',
            args={'entities': entities}
        )

    def _refactoring_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for refactoring queries."""
        target = ''
        if entities.get('class_name'):
            target = entities['class_name'][0]
        elif entities.get('function_name'):
            target = entities['function_name'][0]

        return Action(
            tool='RefactorAnalyzer',
            func='analyze',
            args={'target': target, 'entities': entities}
        )

    def _security_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for security queries."""
        return Action(
            tool='SecurityAnalyzer',
            func='analyze',
            args={'entities': entities}
        )

    def _configuration_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create action for configuration queries."""
        return Action(
            tool='ConfigurationAnalyzer',
            func='analyze',
            args={'entities': entities}
        )

    def _general_action(self, entities: Dict[str, List[str]]) -> Action:
        """Create fallback action for general queries."""
        return Action(
            tool='GeneralAgent',
            func='process',
            args={'entities': entities}
        )
