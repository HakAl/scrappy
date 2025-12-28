Fixed multiple security vulnerabilities in the Agent Loop code:

- Command injection in git checkpoint operations (use argument lists instead of shell=True)
- Path traversal in verifier (validate paths are within project root)
- Dangerous command detection bypass (detect command chaining, substitution, encoding escapes)
- Prompt injection in planner (wrap user input in delimiters with clear instructions)
- LLM-generated step parameter validation (check paths, filenames, command types)
- Dangerous command confirmation bypass (prompt for dangerous commands even after plan approval)
