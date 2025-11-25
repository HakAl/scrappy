"""
Research subtype classification.

Defines the types of research queries to enable appropriate tool selection.
"""

from enum import Enum


class ResearchSubtype(Enum):
    """
    Subtypes of research queries.

    CODEBASE: Questions about project code, files, architecture
        - "What does src/auth.py do?"
        - "Explain the login function"
        - "How does this project handle authentication?"

    GENERAL: General knowledge questions not related to the codebase
        - "Who invented Python?"
        - "What is the best sorting algorithm?"
        - "Who is the best coder, Dijkstra or Turing?"
    """

    CODEBASE = "codebase"
    GENERAL = "general"
