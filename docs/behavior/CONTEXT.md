# Enumeration Approach - src\context.py - tests\test_context.py

## Supported Contexts

```
  Project Types (detected via markers)

  | Type    | Marker Files                           | PromptBuilder Support                    |
  |---------|----------------------------------------|------------------------------------------|
  | Python  | requirements.txt, pyproject.toml       | Yes - pip, venv, pytest guidance         |
  | Java    | pom.xml (Maven), build.gradle (Gradle) | Yes - Maven/Gradle, JUnit guidance       |
  | Node.js | package.json                           | Yes - npm, Jest guidance                 |
  | Go      | go.mod                                 | Yes - go.mod, go test guidance           |
  | Rust    | Cargo.toml                             | Yes - Cargo, crates.io guidance          |
  | Ruby    | Gemfile                                | Detected only (no specific guidance yet) |
  | .NET    | *.csproj                               | Detected only (no specific guidance yet) |
  | Unknown | No markers found                       | Generic guidance                         |

  Platforms

  | Platform   | Detection                | PromptBuilder Support                       |
  |------------|--------------------------|---------------------------------------------|
  | Windows    | sys.platform == 'win32'  | Yes - cmd.exe commands, PowerShell warnings |
  | macOS      | sys.platform == 'darwin' | Yes - Unix commands                         |
  | Linux/Unix | Other                    | Yes - Unix commands                         |

  File Type Categories (in file_index)

  - python: .py
  - javascript: .js, .jsx, .ts, .tsx
  - web: .html, .css, .scss
  - config: .json, .yaml, .yml, .toml, .ini
  - docs: .md, .rst, .txt
  - other: All other files (including extensionless like Gemfile)
```

## Identification Method

  1. Use file_index['config'] to find ALL project markers:
  # Find all package.json, requirements.txt, pom.xml anywhere in tree
  project_markers = [f for f in file_index['config']
                     if any(f.endswith(m) for m in ['package.json', 'pom.xml', ...])]

  2. Detect languages from actual code files:
  has_python = len(file_index['python']) > 0
  has_javascript = len(file_index['javascript']) > 0

  3. Map subdirectories to their project types:
  # 'frontend/package.json' -> frontend is nodejs
  # 'backend/requirements.txt' -> backend is python



