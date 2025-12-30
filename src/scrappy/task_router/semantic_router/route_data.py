"""Canonical examples for semantic routing.

These examples serve as anchor points in vector space for classification.
User input is embedded and classified based on nearest neighbors among these examples.

Categories:
- DIRECT_COMMAND: Shell commands, no agent loop (pip, npm, git, docker, etc.)
- CODE_GENERATION: Write/modify code, full agent with planning
- RESEARCH: Information, explanations, codebase analysis, search
- CONVERSATION: Greetings, thanks, meta-questions
"""

from typing import Dict, List

ROUTE_EXAMPLES: List[Dict[str, str]] = [
    # ==========================================
    # DIRECT_COMMAND
    # Intent: Immediate execution, shell commands, no "thinking" required.
    # ==========================================
    {"text": "pip install requests", "label": "DIRECT_COMMAND"},
    {"text": "npm install react", "label": "DIRECT_COMMAND"},
    {"text": "npm run build", "label": "DIRECT_COMMAND"},
    {"text": "git status", "label": "DIRECT_COMMAND"},
    {"text": "git commit -m 'fix'", "label": "DIRECT_COMMAND"},
    {"text": "docker ps", "label": "DIRECT_COMMAND"},
    {"text": "docker build -t myapp .", "label": "DIRECT_COMMAND"},
    {"text": "pytest", "label": "DIRECT_COMMAND"},
    {"text": "pytest tests/", "label": "DIRECT_COMMAND"},
    {"text": "ls", "label": "DIRECT_COMMAND"},
    {"text": "cd src", "label": "DIRECT_COMMAND"},

    # ==========================================
    # CODE_GENERATION
    # Intent: Complex state modification, file writing, reasoning required.
    # ==========================================
    {"text": "write a python script to parse csv", "label": "CODE_GENERATION"},
    {"text": "create a new node.js server", "label": "CODE_GENERATION"},
    {"text": "add a node.js server", "label": "CODE_GENERATION"},
    {"text": "scaffold a react component", "label": "CODE_GENERATION"},
    {"text": "make a dockerfile for this app", "label": "CODE_GENERATION"},
    {"text": "create a requirements.txt", "label": "CODE_GENERATION"},
    {"text": "generate setup.py", "label": "CODE_GENERATION"},
    {"text": "build a REST API endpoint", "label": "CODE_GENERATION"},
    {"text": "refactor this function to be async", "label": "CODE_GENERATION"},
    {"text": "refactor the authentication module", "label": "CODE_GENERATION"},
    {"text": "fix the type error on line 10", "label": "CODE_GENERATION"},
    {"text": "fix the bug in user login", "label": "CODE_GENERATION"},
    {"text": "debug why the server is crashing", "label": "CODE_GENERATION"},
    {"text": "add error handling to this block", "label": "CODE_GENERATION"},
    {"text": "write unit tests for this class", "label": "CODE_GENERATION"},
    {"text": "implement a function to sort data", "label": "CODE_GENERATION"},
    {"text": "first create a database model, then add the API endpoint", "label": "CODE_GENERATION"},

    # ==========================================
    # RESEARCH
    # Intent: Information retrieval, explanation, "Grepping" for understanding.
    # ==========================================
    {"text": "what is python?", "label": "RESEARCH"},
    {"text": "how does async await work?", "label": "RESEARCH"},
    {"text": "why is my code slow?", "label": "RESEARCH"},
    {"text": "which library should I use?", "label": "RESEARCH"},
    {"text": "explain how JWT authentication works", "label": "RESEARCH"},
    {"text": "describe the MVC pattern", "label": "RESEARCH"},
    {"text": "search for latest langchain updates", "label": "RESEARCH"},
    {"text": "find documentation for fastapi", "label": "RESEARCH"},
    {"text": "find all TODO comments", "label": "RESEARCH"},
    {"text": "list all Python files", "label": "RESEARCH"},
    {"text": "show me the requirements.txt", "label": "RESEARCH"},
    {"text": "analyze the codebase structure", "label": "RESEARCH"},

    # ==========================================
    # CONVERSATION
    # Intent: Routing sink for non-actionable text.
    # ==========================================
    {"text": "hi", "label": "CONVERSATION"},
    {"text": "hello", "label": "CONVERSATION"},
    {"text": "hey there", "label": "CONVERSATION"},
    {"text": "good morning", "label": "CONVERSATION"},
    {"text": "thanks", "label": "CONVERSATION"},
    {"text": "thank you", "label": "CONVERSATION"},
    {"text": "bye", "label": "CONVERSATION"},
    {"text": "goodbye", "label": "CONVERSATION"},
    {"text": "who are you?", "label": "CONVERSATION"},
    {"text": "what can you do?", "label": "CONVERSATION"},
    {"text": "help", "label": "CONVERSATION"},
    {"text": "ok", "label": "CONVERSATION"},
    {"text": "yes", "label": "CONVERSATION"},
    {"text": "no", "label": "CONVERSATION"},
]
