# Context

The context system detects and provides information about the project environment, platform, and codebase structure.

**Source:** `src/context.py` | **Tests:** `tests/test_context.py`

## Supported Contexts

### Project Types

Detected via marker files in the project directory:

| Type | Marker Files | PromptBuilder Support |
|------|--------------|----------------------|
| Python | `requirements.txt`, `pyproject.toml` | pip, venv, pytest guidance |
| Java | `pom.xml` (Maven), `build.gradle` (Gradle) | Maven/Gradle, JUnit guidance |
| Node.js | `package.json` | npm, Jest guidance |
| Go | `go.mod` | go.mod, go test guidance |
| Rust | `Cargo.toml` | Cargo, crates.io guidance |
| Ruby | `Gemfile` | Detected only (no specific guidance yet) |
| .NET | `*.csproj` | Detected only (no specific guidance yet) |
| Unknown | No markers found | Generic guidance |

### Platforms

| Platform | Detection | PromptBuilder Support |
|----------|-----------|----------------------|
| Windows | `sys.platform == 'win32'` | cmd.exe commands, PowerShell warnings |
| macOS | `sys.platform == 'darwin'` | Unix commands |
| Linux/Unix | Other | Unix commands |

### File Type Categories

Used in the file index:

| Category | Extensions |
|----------|------------|
| python | `.py` |
| javascript | `.js`, `.jsx`, `.ts`, `.tsx` |
| web | `.html`, `.css`, `.scss` |
| config | `.json`, `.yaml`, `.yml`, `.toml`, `.ini` |
| docs | `.md`, `.rst`, `.txt` |
| other | All other files (including extensionless like `Gemfile`) |

## Identification Method

### 1. Find Project Markers

```python
# Find all package.json, requirements.txt, pom.xml anywhere in tree
project_markers = [
    f for f in file_index['config']
    if any(f.endswith(m) for m in ['package.json', 'pom.xml', ...])
]
```

### 2. Detect Languages from Code Files

```python
has_python = len(file_index['python']) > 0
has_javascript = len(file_index['javascript']) > 0
```

### 3. Map Subdirectories to Project Types

```python
# 'frontend/package.json' -> frontend is nodejs
# 'backend/requirements.txt' -> backend is python
```

## CodebaseContext API

```python
from src.context import CodebaseContext

context = CodebaseContext(project_path)

# Platform detection
platform = context.get_platform()  # 'windows', 'darwin', 'linux'

# Project type detection
project_type = context.get_project_type()  # 'python', 'nodejs', etc.

# File index
python_files = context.file_index['python']

# Tool detection
has_git = context.has_tool('git')
```

## Usage in Components

### PromptBuilder

```python
from src.agent.prompt_builder import PromptBuilder

builder = PromptBuilder(context)
prompt = builder.build(task="fix the bug")
# Includes platform-specific and project-specific guidance
```

### Platform Utils

```python
from src.platform.platform_utils import translate_command

# Translates commands based on platform context
cmd = translate_command("ls -la", context)
# On Windows: "dir"
```

### Command Tool

```python
from src.agent_tools.tools.command_tool import CommandTool

tool = CommandTool(context=context)
# Uses context for platform-specific command handling
```

## Architecture

```
src/context/
  codebase_context.py   # Main CodebaseContext class
  protocols.py          # Context protocols
  cache.py              # Context caching
  code_chunker.py       # Code chunking for context windows
  file_scanner.py       # File discovery
  git_history.py        # Git history analysis
  project_detector.py   # Project type detection
  semantic/             # Semantic search capabilities
```

## Testing

Context detection is easily testable via mock file systems:

```python
def test_detects_python_project():
    mock_fs = MockFileSystem()
    mock_fs.create_file("requirements.txt", "pytest==7.0")
    mock_fs.create_file("src/main.py", "print('hello')")

    context = CodebaseContext(
        project_path=mock_fs.root,
        file_system=mock_fs,
    )

    assert context.get_project_type() == "python"
    assert "main.py" in context.file_index["python"]
```
