Path escaping/construction.
- tests\test_agent_path_escaping.py

Impact on Original Bug

  The audit log failure where New-Item was "not recognized" would now:
  1. Be rejected during validation with message: "PowerShell cmdlet 'new-item' not available in cmd.exe. Use cmd.exe
   equivalent or Python fallback."
  2. If the path had forward slashes, they would be normalized to backslashes before attempting execution

  The agent will now receive a clear error message instead of a cryptic "not recognized" failure.


src\agent\core.py
  refactor out: parse, plan, retry

  insanity: _tool_run_command --> hardcoded to catch spring dls exactly? npm?