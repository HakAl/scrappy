# Tools

The agent uses tools to interact with the file system, execute commands, search code, and fetch web content. All tools follow the `ToolProtocol` and are managed by the `ToolRegistry`.

## Architecture

```
src/agent_tools/
  tools/
    base.py               # ToolProtocol, ToolBase, ToolResult, ToolContext
    registry.py           # ToolRegistry - central tool management
    file_tools.py         # File operations
    git_tools.py          # Git operations
    search_tools.py       # Code search (pattern-based)
    semantic_search_tool.py # Semantic code search (embeddings)
    web_tools.py          # Web fetch/search
    python_tools.py       # Python-specific tools
    command_tool.py       # Shell command execution
  components/
    command_advisor.py    # Command safety advice
    command_security.py   # Security validation
    output_parser.py      # Output parsing
    platform_sanitizer.py # Platform-specific fixes
    subprocess_runner.py  # Safe subprocess wrapper
```

## Tool Protocol

All tools implement `ToolProtocol`:

```python
class ToolProtocol(Protocol):
    name: str
    description: str
    parameters: List[ToolParameter]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult: ...
```

## Available Tools

### File Operations (`file_tools.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `ReadFileTool` | Read file contents | `path` |
| `WriteFileTool` | Write content to file | `path`, `content` |
| `ListFilesTool` | List files in directory | `path`, `pattern` (optional) |
| `ListDirectoryTool` | Show directory tree | `path`, `depth` (optional) |

### Git Operations (`git_tools.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `GitLogTool` | Show commit history | `count` (optional) |
| `GitStatusTool` | Show repository status | None |
| `GitDiffTool` | Show differences | `ref1`, `ref2` (optional) |
| `GitBlameTool` | Show line-by-line authorship | `path` |
| `GitShowTool` | Show commit details | `ref` |
| `GitRecentChangesTool` | Show recent file changes | `days` (optional) |

### Search Tools (`search_tools.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `SearchCodeTool` | Search code by pattern | `pattern`, `file_type` (optional) |

### Semantic Search Tools (`semantic_search_tool.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `SemanticSearchTool` | Semantic code search using embeddings | `query`, `max_tokens` (optional, default: 4000) |

The semantic search tool (`codebase_search`) finds code based on meaning, not exact text. Use it for conceptual queries like "how does authentication work?" or "find error handling code".

- Requires codebase to be indexed (happens automatically in background on startup)
- Returns relevant code chunks with file paths and line numbers
- Falls back gracefully when index is not ready

See [SEMANTIC_FILE_SEARCH.md](SEMANTIC_FILE_SEARCH.md) for details on the indexing system.

### Web Tools (`web_tools.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `WebFetchTool` | Fetch URL content | `url` |
| `WebSearchTool` | Search the web | `query` |

### Python Tools (`python_tools.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `AnalyzePythonDependenciesTool` | Analyze project dependencies | `path` (optional) |

### Command Execution (`command_tool.py`)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `CommandTool` | Execute shell commands | `command`, `timeout` (optional) |

## Tool Registry

The `ToolRegistry` manages tool registration and lookup:

```python
registry = ToolRegistry()

# Register tools
registry.register(ReadFileTool())
registry.register(WriteFileTool())

# Get tool by name
tool = registry.get("read_file")

# List all tools
tools = registry.list_tools()
```

### Factory Pattern

Use `registry_factory.py` to create a pre-configured registry:

```python
from src.agent_tools.registry_factory import create_tool_registry

registry = create_tool_registry(
    file_system=file_system,
    config=config,
)
```

## Command Tool Security

The `CommandTool` includes multiple safety layers:

### Security Validation (`command_security.py`)

Checks for:
- Dangerous commands (rm -rf, format, etc.)
- Interactive commands requiring user input
- Commands that could damage the system

### Platform Sanitization (`platform_sanitizer.py`)

Handles:
- Windows vs Unix command differences
- Path separator normalization
- Shell-specific escaping

### Output Parsing (`output_parser.py`)

Parses command output to extract:
- Exit codes
- Stdout/stderr
- Error messages

## Tool Results

All tools return `ToolResult`:

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

## Adding New Tools

1. Create a class implementing `ToolProtocol`
2. Define `name`, `description`, and `parameters`
3. Implement the `execute` method
4. Register with the `ToolRegistry`

```python
class MyCustomTool(ToolBase):
    name = "my_tool"
    description = "Does something useful"
    parameters = [
        ToolParameter(name="input", type="string", required=True),
    ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        input_val = kwargs.get("input")
        # Do work...
        return ToolResult(success=True, output="Done")
```

## Testing Tools

Tools are designed for dependency injection, making testing straightforward:

```python
def test_read_file_tool():
    mock_fs = MockFileSystem()
    mock_fs.write("test.txt", "content")

    tool = ReadFileTool(file_system=mock_fs)
    result = tool.execute(context, path="test.txt")

    assert result.success
    assert result.output == "content"
```
