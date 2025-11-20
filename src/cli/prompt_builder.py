"""
Prompt builder for smart query functionality.

Constructs prompts with classification context and research results.
"""

from typing import List, Optional

from .research_handlers.base import ClassificationResult


class PromptBuilder:
    """Builds prompts for LLM with classification context and research results."""

    def build(
        self,
        query: str,
        classification: ClassificationResult,
        research_results: List[str],
        project_summary: Optional[str] = None
    ) -> str:
        """
        Build a prompt with classification context and research results.

        Args:
            query: The user's original query
            classification: The query classification result
            research_results: List of research result strings
            project_summary: Optional project summary to include

        Returns:
            Formatted prompt string for LLM
        """
        # Build classification context
        classification_context = self._build_classification_context(classification)

        # Build the prompt based on whether we have research results
        if research_results:
            # Prepend project summary if available
            results_to_use = list(research_results)
            if project_summary:
                results_to_use.insert(0, f"Project Summary:\n{project_summary}")

            context = "\n\n---\n\n".join(results_to_use)
            prompt = f"""{classification_context}

Research Results:

{context}

---

User Question: {query}

Based on the classification and research findings above, provide a specific, accurate, and helpful answer. Reference specific files, functions, or code patterns when relevant."""
        else:
            # No research results - simpler prompt
            if project_summary:
                prompt = f"""{classification_context}

Project Summary:
{project_summary}

User Question: {query}

Provide a helpful answer based on your understanding of the query intent."""
            else:
                prompt = f"""{classification_context}

User Question: {query}

Provide a helpful answer based on your understanding of the query intent."""

        return prompt

    def _build_classification_context(
        self,
        classification: ClassificationResult
    ) -> str:
        """
        Build classification context string.

        Args:
            classification: The query classification result

        Returns:
            Formatted classification context string
        """
        # Format entities
        entities_str = ', '.join([
            f"{k}: {v}"
            for k, v in classification.entities.items()
            if v
        ])
        if not entities_str:
            entities_str = "none"

        # Format keywords
        keywords_str = ', '.join(classification.keywords[:10])
        if not keywords_str:
            keywords_str = "none"

        return f"""Query Classification:
- Primary Intent: {classification.intent_result.intent.value} (confidence: {classification.intent_result.confidence:.2f})
- Key entities: {entities_str}
- Keywords: {keywords_str}"""

    def get_system_prompt(self) -> str:
        """
        Get the system prompt for smart query responses.

        Returns:
            System prompt string
        """
        return (
            "You are a helpful AI assistant with access to codebase research and "
            "query intent classification. Use the classification context and research "
            "findings to give specific, accurate answers. Always explain your reasoning "
            "based on the evidence found."
        )
