
4 - Database Query Tool

  - Execute SQL queries (SELECT only for safety)
  - Schema introspection
  - Would enable: "Show me the users table structure"

5 - Dependency Analysis Tool

  - Parse package.json/requirements.txt/etc
  - Check outdated packages, security vulnerabilities
  - Would enable: "Check for vulnerable dependencies"

  ---

  Enhancements to Existing Tools

  Run Command

  - Add streaming output for all commands (not just long-running)
  - Better error recovery with retry logic
  - Output format parsing (JSON/YAML auto-detection)

  Git Tools

  - Add git_stash tool for temporary changes
  - Add git_branch for branch management
  - PR/Issue integration with GitHub API

  File Operations

  - Batch operations (read multiple files at once)
  - Diff preview before write_file
  - File watching for continuous monitoring
