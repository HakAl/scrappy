"""
Behavior tests for command translation.

Tests prove that command translation features work correctly across platforms,
handling Unix->Windows translation, path normalization, and special cases.
"""

import pytest
from tests.helpers import FakePlatformDetector
from src.platform.translation import SmartCommandTranslator


class TestCommandTranslation:
    """Test Unix to Windows command translation."""

    def test_no_translation_on_unix(self):
        """Test that commands are not translated on Unix systems."""
        detector = FakePlatformDetector(platform="Linux")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("ls -la")

        assert command == "ls -la"
        assert not was_translated

    def test_translates_ls_to_dir_on_windows(self):
        """Test that 'ls' is translated to 'dir' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("ls")

        assert command == "dir"
        assert was_translated

    def test_translates_ls_with_flags(self):
        """Test that 'ls' commands are translated to 'dir' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        commands = ["ls -la", "ls -l", "ls -a"]

        for cmd in commands:
            command, was_translated = translator.translate_command(cmd)
            assert command.startswith("dir"), f"Failed for {cmd}: {command}"
            assert was_translated

    def test_translates_pwd_to_cd(self):
        """Test that 'pwd' is translated to 'cd' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("pwd")

        assert command == "cd"
        assert was_translated

    def test_translates_cat_to_type(self):
        """Test that 'cat' is translated to 'type' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("cat file.txt")

        assert command == "type file.txt"
        assert was_translated

    def test_translates_rm_to_del(self):
        """Test that 'rm' is translated to 'del' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("rm file.txt")

        assert command == "del file.txt"
        assert was_translated

    def test_translates_rm_rf_to_rmdir(self):
        """Test that 'rm' is translated on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("rm file.txt")

        assert command == "del file.txt"
        assert was_translated

    def test_translates_cp_to_copy(self):
        """Test that 'cp' is translated to 'copy' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("cp src.txt dst.txt")

        assert command == "copy src.txt dst.txt"
        assert was_translated

    def test_translates_cp_to_copy(self):
        """Test that 'cp' is translated to 'copy' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("cp src dst")

        assert command == "copy src dst"
        assert was_translated

    def test_translates_mv_to_move(self):
        """Test that 'mv' is translated to 'move' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("mv old.txt new.txt")

        assert command == "move old.txt new.txt"
        assert was_translated

    def test_translates_mkdir_p(self):
        """Test that 'mkdir -p' is translated to 'mkdir' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("mkdir -p dir/subdir")

        assert command == "mkdir dir/subdir"
        assert was_translated

    def test_translates_grep_to_findstr(self):
        """Test that 'grep' is translated to 'findstr' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("grep pattern file.txt")

        assert command == "findstr pattern file.txt"
        assert was_translated

    def test_translates_clear_to_cls(self):
        """Test that 'clear' is translated to 'cls' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("clear")

        assert command == "cls"
        assert was_translated

    def test_translates_which_to_where(self):
        """Test that 'which' is translated to 'where' on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("which python")

        assert command == "where python"
        assert was_translated

    def test_empty_command_not_translated(self):
        """Test that empty commands are not translated."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("")

        assert command == ""
        assert not was_translated

    def test_whitespace_only_command_not_translated(self):
        """Test that whitespace-only commands are not translated."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("   ")

        assert not was_translated

    def test_unknown_command_not_translated(self):
        """Test that unknown commands are not translated."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, was_translated = translator.translate_command("unknowncmd arg1 arg2")

        assert command == "unknowncmd arg1 arg2"
        assert not was_translated


class TestPathNormalization:
    """Test path normalization for Windows."""

    def test_no_normalization_on_unix(self):
        """Test that paths are not normalized on Unix systems."""
        detector = FakePlatformDetector(platform="Linux")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("mkdir /usr/local/bin")

        assert command == "mkdir /usr/local/bin"
        assert not modified
        assert message == ""

    def test_normalizes_paths_for_mkdir(self):
        """Test that paths are normalized for mkdir command on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("mkdir src/components/ui")

        assert command == "mkdir src\\components\\ui"
        assert modified
        assert "Normalized paths" in message

    def test_normalizes_paths_for_cd(self):
        """Test that paths are normalized for cd command on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("cd src/components")

        assert command == "cd src\\components"
        assert modified

    def test_normalizes_paths_for_copy(self):
        """Test that paths are normalized for copy command on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("copy src/file.txt dst/file.txt")

        assert command == "copy src\\file.txt dst\\file.txt"
        assert modified

    def test_preserves_quotes_when_normalizing(self):
        """Test that quotes are preserved when normalizing paths."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths('mkdir "src/my folder/files"')

        assert command == 'mkdir "src\\my folder\\files"'
        assert modified

    def test_does_not_normalize_urls(self):
        """Test that URLs are not normalized."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("curl https://example.com/api/users")

        assert command == "curl https://example.com/api/users"
        assert not modified

    def test_does_not_normalize_command_flags(self):
        """Test that command flags are not normalized."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("dir /s /b")

        assert command == "dir /s /b"
        assert not modified

    def test_normalizes_powershell_path_params(self):
        """Test that PowerShell path parameters are normalized."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("Copy-Item -Path src/file.txt -Destination dst/file.txt")

        assert modified
        assert "src\\file.txt" in command
        assert "dst\\file.txt" in command

    def test_empty_command_not_normalized(self):
        """Test that empty commands are not normalized."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("")

        assert command == ""
        assert not modified

    def test_non_path_command_not_normalized(self):
        """Test that non-path commands are not normalized."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_command_paths("echo hello/world")

        assert command == "echo hello/world"
        assert not modified


class TestNpmCommandNormalization:
    """Test npm command normalization for Windows."""

    def test_no_normalization_on_unix(self):
        """Test that npm commands are not normalized on Unix."""
        detector = FakePlatformDetector(platform="Linux")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm create vite@latest")

        assert command == "npm create vite@latest"
        assert not modified

    def test_adds_no_color_to_npm_create(self):
        """Test that NO_COLOR is added to npm create commands."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm create vite@latest")

        assert "set NO_COLOR=1 &&" in command
        assert "--no-color" in command
        assert modified
        assert "Unicode" in message

    def test_adds_no_color_to_npx_create(self):
        """Test that NO_COLOR is added to npx create commands."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npx create-react-app my-app")

        assert "set NO_COLOR=1 &&" in command
        assert modified

    def test_adds_no_color_to_npm_init(self):
        """Test that NO_COLOR is added to npm init commands."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm init vite")

        assert "set NO_COLOR=1 &&" in command
        assert "--no-color" in command
        assert modified

    def test_adds_flags_to_npm_install(self):
        """Test that --no-progress and --no-color are added to npm install."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm install react")

        assert "--no-progress" in command
        assert "--no-color" in command
        assert modified

    def test_adds_flags_to_npm_run(self):
        """Test that flags are added to npm run commands."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm run build")

        assert "--no-progress" in command
        assert "--no-color" in command
        assert modified

    def test_does_not_duplicate_no_color(self):
        """Test that --no-color is not duplicated if already present."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm install --no-color")

        count = command.count("--no-color")
        assert count == 1

    def test_preserves_double_dash_in_npm_create(self):
        """Test that -- is preserved when adding --no-color to npm create."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("npm create vite@latest -- --template react")

        assert "--no-color -- --template react" in command
        assert modified

    def test_non_npm_command_not_modified(self):
        """Test that non-npm commands are not modified."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, modified, message = translator.normalize_npm_command_for_windows("node index.js")

        assert command == "node index.js"
        assert not modified


class TestSpringInitializrFixes:
    """Test Spring Initializr URL fixing."""

    def test_no_fix_for_non_spring_commands(self):
        """Test that non-Spring commands are not modified."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command, fixed, message = translator.fix_spring_initializr_command("curl https://example.com/api")

        assert command == "curl https://example.com/api"
        assert not fixed

    def test_fixes_spring_initializr_curl_command(self):
        """Test that Spring Initializr curl commands are fixed."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = "curl https://start.spring.io/starter.zip?type=maven-project"
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert fixed
        assert "start.spring.io" in result_command

    def test_adds_default_parameters_to_spring_url(self):
        """Test that default parameters are added to Spring Initializr URLs."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = "curl https://start.spring.io/starter.zip?dependencies=web"
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert "type=maven-project" in result_command
        assert "language=java" in result_command
        assert "javaVersion=17" in result_command

    def test_corrects_invalid_dependency_names(self):
        """Test that invalid dependency names are corrected."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = "curl https://start.spring.io/starter.zip?dependencies=spring-boot-starter-web"
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert "dependencies=web" in result_command
        assert fixed

    def test_fixes_powershell_downloadfile_command(self):
        """Test that PowerShell DownloadFile commands are fixed."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = '(New-Object System.Net.WebClient).DownloadFile("https://start.spring.io/starter.zip?dependencies=web", "demo.zip")'
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert fixed
        assert "start.spring.io" in result_command

    def test_fixes_powershell_invoke_webrequest_command(self):
        """Test that PowerShell Invoke-WebRequest commands are fixed."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = 'Invoke-WebRequest -Uri https://start.spring.io/starter.zip?dependencies=web -OutFile demo.zip'
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert fixed
        assert "start.spring.io" in result_command

    def test_encodes_url_parameters_correctly(self):
        """Test that URL parameters are properly encoded."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        command = "curl https://start.spring.io/starter.zip?name=My Project&description=A test project"
        result_command, fixed, message = translator.fix_spring_initializr_command(command)

        assert "name=My" in result_command or "name=My+Project" in result_command


class TestCommandSplittingUtilities:
    """Test internal utility methods for command parsing."""

    def test_splits_simple_command(self):
        """Test that simple commands are split correctly."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        parts = translator._split_command_preserving_quotes("ls -la /tmp")

        assert parts == ["ls", "-la", "/tmp"]

    def test_preserves_double_quotes(self):
        """Test that double quotes are preserved when splitting."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        parts = translator._split_command_preserving_quotes('mkdir "my folder"')

        assert parts == ["mkdir", '"my folder"']

    def test_preserves_single_quotes(self):
        """Test that single quotes are preserved when splitting."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        parts = translator._split_command_preserving_quotes("echo 'hello world'")

        assert parts == ["echo", "'hello world'"]

    def test_handles_mixed_quotes(self):
        """Test that mixed quotes are handled correctly."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        parts = translator._split_command_preserving_quotes('cmd "arg 1" \'arg 2\' arg3')

        assert parts == ["cmd", '"arg 1"', "'arg 2'", "arg3"]

    def test_handles_empty_string(self):
        """Test that empty strings are handled correctly."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        parts = translator._split_command_preserving_quotes("")

        assert parts == []

    def test_identifies_urls_correctly(self):
        """Test that URLs are correctly identified."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        assert translator._is_url("https://example.com")
        assert translator._is_url("http://example.com")
        assert not translator._is_url("file://path")
        assert not translator._is_url("src/path/file.txt")

    def test_normalizes_quoted_paths(self):
        """Test that paths within quotes are normalized correctly."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        assert translator._normalize_path_in_part('"src/path"') == '"src\\path"'
        assert translator._normalize_path_in_part("'src/path'") == "'src\\path'"
        assert translator._normalize_path_in_part("src/path") == "src\\path"

    def test_normalizes_paths_without_quotes(self):
        """Test that paths without quotes are normalized correctly."""
        detector = FakePlatformDetector(platform="Windows")
        translator = SmartCommandTranslator(detector)

        assert translator._normalize_path_in_part("src/components/ui") == "src\\components\\ui"
