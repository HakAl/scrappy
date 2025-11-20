"""
Command translation implementation.

Provides platform-specific command translation to enable cross-platform
command execution (e.g., translating Unix commands to Windows equivalents).
"""

import re
from typing import Tuple, Dict, List, Any, Optional
from urllib.parse import quote_plus

from src.platform.protocols.translation import CommandTranslatorProtocol
from src.platform.protocols.detection import PlatformDetectorProtocol


class SmartCommandTranslator:
    """
    Concrete implementation of command translation protocol.

    Translates Unix commands to Windows equivalents, normalizes paths,
    and fixes platform-specific command issues.

    All dependencies are injected via constructor to enable testing.
    """

    def __init__(
        self,
        detector: PlatformDetectorProtocol
    ):
        """
        Initialize the command translator.

        Args:
            detector: Platform detector to determine current platform.
        """
        self._detector = detector

    def translate_command(self, command: str) -> Tuple[str, bool]:
        """
        Translate Unix commands to Windows equivalents when necessary.

        Args:
            command: Original command

        Returns:
            Tuple of (translated_command, was_translated)
        """
        if not self._detector.is_windows():
            return command, False

        translations = {
            'ls': 'dir',
            'ls -la': 'dir',
            'ls -l': 'dir',
            'ls -a': 'dir /a',
            'pwd': 'cd',
            'cat': 'type',
            'rm': 'del',
            'rm -rf': 'rmdir /s /q',
            'cp': 'copy',
            'cp -r': 'xcopy /e /i',
            'mv': 'move',
            'mkdir -p': 'mkdir',
            'touch': 'type nul >',
            'grep': 'findstr',
            'clear': 'cls',
            'which': 'where',
        }

        cmd_parts = command.strip().split()
        if not cmd_parts:
            return command, False

        base_cmd = cmd_parts[0].lower()

        for unix_cmd, win_cmd in translations.items():
            if command.strip().lower().startswith(unix_cmd):
                new_cmd = win_cmd + command[len(unix_cmd):]
                return new_cmd, True

        if base_cmd in translations:
            new_cmd = translations[base_cmd] + command[len(base_cmd):]
            return new_cmd, True

        return command, False

    def normalize_command_paths(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize paths in shell commands for the current platform.

        On Windows, converts forward slashes to backslashes in path arguments.

        Args:
            command: Shell command that may contain paths

        Returns:
            Tuple of (normalized_command, was_modified, message)
        """
        if not self._detector.is_windows():
            return command, False, ""

        original_command = command

        path_commands = [
            'mkdir', 'md', 'rmdir', 'rd', 'cd', 'dir', 'copy', 'xcopy',
            'move', 'del', 'erase', 'type', 'more', 'attrib'
        ]

        powershell_path_params = [
            '-Path', '-LiteralPath', '-Destination', '-Source', '-FilePath',
            '-OutputPath', '-InputPath', '-TargetPath'
        ]

        parts = self._split_command_preserving_quotes(command)

        if not parts:
            return command, False, ""

        base_cmd = parts[0].lower()

        is_path_command = any(
            base_cmd == cmd or base_cmd.endswith('\\' + cmd)
            for cmd in path_commands
        )

        has_powershell_path_param = any(
            any(part.lower() == param.lower() for param in powershell_path_params)
            for part in parts
        )

        if not is_path_command and not has_powershell_path_param:
            return command, False, ""

        modified = False
        new_parts = [parts[0]]
        next_is_path = False

        for part in parts[1:]:
            is_path_param = any(
                part.lower() == param.lower()
                for param in powershell_path_params
            )

            if is_path_param:
                new_parts.append(part)
                next_is_path = True
                continue

            if next_is_path:
                next_is_path = False
                if '/' in part and not self._is_url(part):
                    normalized = self._normalize_path_in_part(part)
                    new_parts.append(normalized)
                    modified = True
                else:
                    new_parts.append(part)
                continue

            if (part.startswith('-') or part.startswith('/')) and not is_path_command:
                new_parts.append(part)
                continue

            if is_path_command and '/' in part and not self._is_url(part):
                if part.startswith('/') and len(part) <= 3 and '/' not in part[1:]:
                    new_parts.append(part)
                    continue

                normalized = self._normalize_path_in_part(part)
                new_parts.append(normalized)
                modified = True
            else:
                new_parts.append(part)

        if modified:
            new_command = ' '.join(new_parts)
            message = f"Normalized paths for Windows: {original_command} -> {new_command}"
            return new_command, True, message

        return command, False, ""

    def normalize_npm_command_for_windows(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize npm commands for Windows to prevent Unicode output issues.

        Args:
            command: npm command to normalize

        Returns:
            Tuple of (normalized_command, was_modified, message)
        """
        if not self._detector.is_windows():
            return command, False, ""

        modified = False

        npm_create_patterns = [
            r'npm\s+create\s+',
            r'npx\s+create-',
            r'npm\s+init\s+',
        ]

        for pattern in npm_create_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                if 'NO_COLOR=' not in command and 'set NO_COLOR' not in command:
                    command = f'set NO_COLOR=1 && {command}'
                    modified = True

                if '--no-color' not in command and 'npm' in command:
                    if ' -- ' in command:
                        parts = command.split(' -- ', 1)
                        command = f'{parts[0]} --no-color -- {parts[1]}'
                    else:
                        command = command.rstrip() + ' --no-color'
                    modified = True
                break

        if re.search(r'npm\s+(install|i|run|start|build|test)', command, re.IGNORECASE):
            if '--no-progress' not in command:
                command = command.rstrip() + ' --no-progress'
                modified = True
            if '--no-color' not in command:
                command = command.rstrip() + ' --no-color'
                modified = True

        if modified:
            message = "Added Windows npm flags to suppress Unicode output"
            return command, True, message

        return command, False, ""

    def fix_spring_initializr_command(self, command: str) -> Tuple[str, bool, str]:
        """
        Fix curl/PowerShell commands that use Spring Initializr.

        Args:
            command: The shell command to fix

        Returns:
            Tuple of (fixed_command, was_fixed, message)
        """
        if 'start.spring.io' not in command:
            return command, False, ""

        curl_match = re.search(
            r'curl\s+[^"\']*["\']?(https?://start\.spring\.io[^"\'\s]+)["\']?',
            command
        )
        if curl_match:
            url = curl_match.group(1).strip("'\"")
            is_valid, fixed_url, error = self._validate_spring_initializr_url(url)

            if not is_valid or url != fixed_url:
                fixed_command = command.replace(url, f'"{fixed_url}"')
                message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
                return fixed_command, True, message

        ps_match = re.search(r'DownloadFile\s*\(\s*["\']([^"\']+)["\']', command)
        if ps_match:
            url = ps_match.group(1)
            is_valid, fixed_url, error = self._validate_spring_initializr_url(url)

            if not is_valid or url != fixed_url:
                fixed_command = command.replace(url, fixed_url)
                message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
                return fixed_command, True, message

        iwr_match = re.search(
            r'-Uri\s+["\']?([^"\'\s]+start\.spring\.io[^"\'\s]+)["\']?',
            command
        )
        if iwr_match:
            url = iwr_match.group(1).strip("'\"")
            is_valid, fixed_url, error = self._validate_spring_initializr_url(url)

            if not is_valid or url != fixed_url:
                fixed_command = command.replace(url, f'"{fixed_url}"')
                message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
                return fixed_command, True, message

        return command, False, ""

    def _split_command_preserving_quotes(self, command: str) -> list[str]:
        """
        Split command into parts while preserving quotes.

        Args:
            command: Command string to split

        Returns:
            List of command parts
        """
        parts = []
        current = ""
        in_quote = False
        quote_char = None

        for char in command:
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
                current += char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
                current += char
            elif char == ' ' and not in_quote:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char

        if current:
            parts.append(current)

        return parts

    def _is_url(self, part: str) -> bool:
        """Check if a string part is a URL."""
        return part.startswith('http://') or part.startswith('https://')

    def _normalize_path_in_part(self, part: str) -> str:
        """Normalize path in a command part, preserving quotes."""
        if part.startswith('"') and part.endswith('"'):
            inner = part[1:-1]
            normalized = inner.replace('/', '\\')
            return f'"{normalized}"'
        elif part.startswith("'") and part.endswith("'"):
            inner = part[1:-1]
            normalized = inner.replace('/', '\\')
            return f"'{normalized}'"
        else:
            return part.replace('/', '\\')

    def _validate_spring_initializr_url(self, url: str) -> Tuple[bool, str, str]:
        """
        Validate and fix Spring Initializr URLs.

        Args:
            url: The Spring Initializr URL to validate

        Returns:
            Tuple of (is_valid, fixed_url, error_message)
        """
        if 'start.spring.io' not in url:
            return True, url, ""

        if '?' not in url:
            return True, url, ""

        base_url, query_string = url.split('?', 1)

        params = {}
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value

        valid_params = {
            'type': ['maven-project', 'gradle-project', 'gradle-project-kotlin'],
            'language': ['java', 'kotlin', 'groovy'],
            'bootVersion': None,
            'baseDir': None,
            'groupId': None,
            'artifactId': None,
            'name': None,
            'description': None,
            'packageName': None,
            'packaging': ['jar', 'war'],
            'javaVersion': ['8', '11', '17', '21'],
            'dependencies': None,
        }

        fixed_params = {}
        errors = []

        for key, value in params.items():
            if key == 'dependencies':
                deps = value.split(',')
                clean_deps = []
                for dep in deps:
                    clean_dep = dep.strip().lower()
                    corrections = {
                        'jjwt': 'security',
                        'jwt': 'security',
                        'spring-boot-starter-web': 'web',
                        'spring-boot-starter-data-jpa': 'data-jpa',
                        'spring-boot-starter-security': 'security',
                        'spring-boot-starter-validation': 'validation',
                    }
                    if clean_dep in corrections:
                        clean_dep = corrections[clean_dep]
                    if clean_dep:
                        clean_deps.append(clean_dep)
                fixed_params[key] = ','.join(clean_deps)
            elif key in valid_params and valid_params[key] is not None:
                if value not in valid_params[key]:
                    errors.append(
                        f"Invalid {key}: {value}. Must be one of {valid_params[key]}"
                    )
                else:
                    fixed_params[key] = value
            else:
                fixed_params[key] = quote_plus(value, safe='')

        defaults = {
            'type': 'maven-project',
            'language': 'java',
            'bootVersion': '3.2.0',
            'packaging': 'jar',
            'javaVersion': '17',
            'groupId': 'com.example',
            'artifactId': 'demo',
            'name': 'demo',
        }

        for key, default in defaults.items():
            if key not in fixed_params:
                fixed_params[key] = default

        fixed_query = '&'.join(f"{k}={v}" for k, v in fixed_params.items())
        fixed_url = f"{base_url}?{fixed_query}"

        if errors:
            return False, fixed_url, "; ".join(errors)

        return True, fixed_url, ""

    def intercept_spring_initializr_download(
        self,
        command: str,
        target_dir: str = "."
    ) -> Optional[Dict[str, Any]]:
        """
        Intercept Spring Initializr download commands and suggest local templates.

        Args:
            command: Shell command that might be downloading from Spring Initializr
            target_dir: Directory where the project should be created

        Returns:
            Dict with intercept info or None if not a Spring Initializr command
        """
        from typing import Dict, Any, Optional

        if 'start.spring.io' not in command:
            return None

        params = {
            'group_id': 'com.example',
            'artifact_id': 'demo',
            'package_name': 'com.example.demo',
            'dependencies': ['web', 'data-jpa', 'h2', 'validation', 'security']
        }

        url_match = re.search(r'https?://start\.spring\.io[^"\'\s]+', command)
        if url_match:
            url = url_match.group(0)
            if '?' in url:
                query = url.split('?', 1)[1]
                for param in query.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        if key == 'groupId':
                            params['group_id'] = value
                        elif key == 'artifactId':
                            params['artifact_id'] = value
                        elif key == 'packageName':
                            params['package_name'] = value
                        elif key == 'dependencies':
                            params['dependencies'] = value.split(',')
                        elif key == 'baseDir':
                            params['artifact_id'] = value

        return {
            'should_intercept': True,
            'reason': 'Spring Initializr downloads often fail on Windows',
            'suggested_action': 'Use write_file to create Spring Boot project files',
            'template_params': params,
            'original_command': command
        }

    def get_spring_boot_fallback_files(
        self,
        group_id: str = "com.example",
        artifact_id: str = "demo",
        package_name: str = "com.example.demo",
        dependencies: List[str] = None
    ) -> Dict[str, str]:
        """
        Generate fallback Spring Boot project files.

        Args:
            group_id: Maven group ID
            artifact_id: Maven artifact ID
            package_name: Java package name
            dependencies: List of dependencies

        Returns:
            Dict mapping file paths to file contents
        """
        from typing import Dict, List

        if dependencies is None:
            dependencies = ['web', 'data-jpa', 'h2', 'validation', 'security']

        package_path = package_name.replace('.', '/')
        files = {}

        # Build dependency XML
        dep_xml = ""
        if 'web' in dependencies:
            dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
"""
        if 'data-jpa' in dependencies:
            dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
"""
        if 'h2' in dependencies:
            dep_xml += """        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
"""
        if 'validation' in dependencies:
            dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
"""
        if 'security' in dependencies:
            dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
"""

        # pom.xml
        files['pom.xml'] = f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>{artifact_id}</name>
    <description>Spring Boot Application</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
{dep_xml}        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
'''

        # Main application class
        class_name = ''.join(
            word.capitalize()
            for word in artifact_id.replace('-', ' ').split()
        )

        files[f'src/main/java/{package_path}/{class_name}Application.java'] = f'''package {package_name};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {class_name}Application {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}Application.class, args);
    }}
}}
'''

        # application.properties
        files['src/main/resources/application.properties'] = '''spring.application.name=demo
server.port=8080

spring.datasource.url=jdbc:h2:mem:testdb
spring.datasource.driverClassName=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.h2.console.enabled=true

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
'''

        # .gitignore
        files['.gitignore'] = '''target/
.mvn/
.idea/
*.iml
.vscode/
'''

        return files
