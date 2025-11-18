# Context

**Enumeration Approach - src\context.py - tests\test_context.py**

## Issues

<!-- EXISITING ISSUE -->
- context summary file always written, doesn't respect user choice
- Auto-explore Stale Context: Uses cached context from llm_team itself, not the new project

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

---


<!-- TODO -->


<!-- new features -->
- Project-based auto-resume
- Add research result caching - Store findings for action phase to use

Refactoring Plan

  Core Principle

  Functions accept CodebaseContext directly - no bridge service, no extra layers. Simple and pragmatic.

  Changes to Make

  1. platform_utils.py - Update function signatures

  Before:
  def is_windows():
      return platform.system() == "Windows"

  def translate_command_for_platform(command):
      if is_windows():
          # translate

  After:
  def translate_command(command: str, context: CodebaseContext) -> str:
      """Translate command for target platform."""
      if context.get_platform() == 'windows':
          # translate
      return command

  def validate_command(command: str, context: CodebaseContext) -> tuple[bool, str]:
      """Validate command is safe for platform."""
      platform = context.get_platform()
      # validation logic

  Key changes:
  - Functions accept context: CodebaseContext parameter
  - Use context.get_platform() instead of calling platform.system()
  - Use context.has_tool('bash') instead of detecting tools
  - Keep the logic the same, just change the data source

  2. command_tool.py - Pass context to platform_utils

  Before:
  from ...platform_utils import is_windows, translate_command_for_platform

  result = translate_command_for_platform(command)

  After:
  from src.context import CodebaseContext
  from ...platform_utils import translate_command

  self.context = CodebaseContext(project_path)
  result = translate_command(command, self.context)

  3. task_router/classifier.py - DEFER THIS

  Skip for now - you're cleaning this up anyway. Add context later when you refactor it.

  4. agent_config.py - Minimal changes

  These functions just return constants, probably don't need context:
  get_dangerous_commands()  # Returns list of strings
  get_interactive_commands()  # Returns list of strings

  No changes needed unless they depend on platform.

  5. Clean up direct platform checks

  llm_team.py:16
  # Before
  if sys.platform == 'win32':

  # After
  from src.context import CodebaseContext
  context = CodebaseContext(Path.cwd())
  if context.get_platform() == 'windows':

  agent/audit.py
  # Before
  if sys.platform != 'win32':

  # After
  if self.context.get_platform() != 'windows':

  6. Update tests

  test_platform_utils.py - Pass mock context:
  # Before
  result = translate_command_for_platform("ls")

  # After
  from unittest.mock import Mock
  mock_context = Mock()
  mock_context.get_platform.return_value = 'windows'
  result = translate_command("ls", mock_context)

  Order of Execution

  1. Update platform_utils.py - Add context parameter to functions
  2. Update command_tool.py - Pass context
  3. Update agent_config.py - Minimal (if needed)
  4. Clean up llm_team.py and audit.py - Replace direct checks
  5. Update tests - Pass mock context
  6. task_router/classifier.py - Defer until after your cleanup

  What You Get

  - ✅ Single source of truth for platform detection (context.py)
  - ✅ No duplication of platform checks
  - ✅ Cached detection (fast)
  - ✅ Simple, pythonic approach (no extra layers)
  - ✅ Still testable (mock context)
  - ⏸️ task_router/classifier.py - Refactor after you clean it up and add better tests


---

  Scope

    Production Code (Main Impact)

  Files that import platform_utils (need updates):

  1. src/agent_config.py (line 10)
    - Imports: get_dangerous_commands, get_interactive_commands
    - Impact: LOW - these are just data getters, might not need context
  2. src/agent/core.py (line 49)
    - Imports: get_platform_name, is_windows, validate_command_for_platform
    - Impact: UNKNOWN - need to check if actually used (grep found no usage!)
  3. src/agent_tools/tools/command_tool.py (line 24)
    - Imports: 6+ functions (main user of platform_utils)
    - Impact: HIGH - this is the heavy user
  4. src/task_router/classifier.py (line 10)
    - Imports: is_windows, validate_command_for_platform
    - Impact: MEDIUM - uses in validation logic

  Files that already have CodebaseContext:

  1. src/orchestrator/core.py - ✅ already creates context
  2. src/agent/prompt_builder.py - ✅ already uses context

  Direct platform checks to clean up:

  1. llm_team.py:16 - if sys.platform == 'win32':
  2. src/agent/audit.py:76,92 - sys.platform checks
  3. src/agent_tools/tools/command_tool.py:38 - fallback os.name == 'nt'

  Test Files (Secondary Impact)

  - tests/test_platform_utils.py - Will need updates to pass mock context
  - tests/test_agent_*.py - Various platform_utils usage
  - Direct sys.platform checks in tests are fine (tests can do direct checks)

  Actual Scope Assessment

  Core changes:
  1. ✅ Update platform_utils.py function signatures (~30 functions)
  2. ✅ Update command_tool.py to pass context
  3. ✅ Update classifier.py to pass context
  4. ✅ Update agent_config.py (minimal - just data getters)
  5. ✅ Clean up unused imports in agent/core.py
  6. ✅ Replace direct platform checks in llm_team.py and audit.py

  Test updates:
  7. ✅ Update test_platform_utils.py (main test file)
  8. ✅ Update other tests that call platform_utils


  ---

**MOAR FEATURES**

- - File watching for continuous monitoring

### High-Priority Additions:

Here are contexts that are highly prevalent in modern software development and would offer immediate value to a broad range of users.

| Type | Marker Files | PromptBuilder Support |
| --- | --- | --- |
| **PHP** | `composer.json`, `php.ini`, `.env` | Yes - Composer (dependency management), PHPUnit (testing), guidance on popular frameworks like Laravel (`artisan` commands) and Symfony (`symfony` CLI). |
| **C++** | `CMakeLists.txt`, `.vcxproj` (Visual Studio), `Makefile` | Yes - Guidance on CMake, vcpkg (dependency management), and popular testing frameworks like Google Test and Catch2. |
| **Swift** | `Package.swift`, `.xcodeproj`, `.xcworkspace`, `.xcconfig` | Yes - Swift Package Manager (SPM) guidance, XCTest (testing framework) support, and assistance with Xcode build configurations. |
| **Kotlin** | `build.gradle.kts` (Gradle for Kotlin), `pom.xml` (Maven) | Yes - Enhanced Gradle/Maven support for Kotlin-specific dependencies and plugins, guidance on testing with JUnit and Mockito. |
| **TypeScript** | `tsconfig.json`, `package.json` | Yes - Deeper integration with `tsc` (the TypeScript compiler), guidance on popular testing frameworks like Jest and Mocha, and support for common frameworks like Angular (`angular.json`) and Vue.js. |
| **Mobile (Cross-Platform)** | | |
| &nbsp;&nbsp;&nbsp;Flutter | `pubspec.yaml` | Yes - Guidance on `flutter pub` commands, `flutter test` for unit and widget testing, and integration with popular state management libraries. |
| &nbsp;&nbsp;&nbsp;React Native | `package.json` | Yes - Similar to Node.js but with specific guidance for React Native CLI, Metro bundler, and testing with Jest and React Native Testing Library. |

### Broadening Framework Support:

Beyond base languages, providing specific guidance for popular frameworks within your existing supported languages can significantly improve the user experience.

| Type | Marker Files | PromptBuilder Support |
| --- | --- | --- |
| **JavaScript/TypeScript Frameworks** | | |
| &nbsp;&nbsp;&nbsp;Angular | `angular.json`, `tsconfig.json` | Yes - Angular CLI (`ng`) commands, Karma and Jasmine for testing, and guidance on component and service generation. |
| &nbsp;&nbsp;&nbsp;Vue.js | `vue.config.js`, `package.json` | Yes - Vue CLI (`vue`) commands, guidance on testing with Vue Test Utils and Jest/Mocha, and support for state management with Pinia. |
| &nbsp;&nbsp;&nbsp;React.js | `package.json` (often with Create React App scripts) | Yes - Guidance on Create React App, Next.js, or Vite, testing with Jest and React Testing Library, and state management with Redux or Zustand. |
| **Python Frameworks** | | |
| &nbsp;&nbsp;&nbsp;Django | `manage.py`, `settings.py` | Yes - Guidance on `manage.py` commands (e.g., `runserver`, `makemigrations`), Django's built-in testing framework, and Django REST framework. |
| **PHP Frameworks** | | |
| &nbsp;&nbsp;&nbsp;Laravel | `artisan`, `composer.json` | Yes - `artisan` command assistance, PHPUnit testing integration, and guidance on Blade templating and Eloquent ORM. |

### Emerging and Specialized Technologies:

To cater to forward-looking developers and those in specialized fields, consider adding support for these languages.

| Type | Marker Files | PromptBuilder Support |
| --- | --- | --- |
| **Scala** | `build.sbt`, `pom.xml` | Detected only (or with guidance on SBT, ScalaTest, and popular frameworks like Akka and Play). |
| **Dart** | `pubspec.yaml`, `analysis_options.yaml` | Detected only (or with guidance on `dart pub` and `dart test`). |
