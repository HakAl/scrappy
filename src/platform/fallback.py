"""
Python fallback command implementations.

Provides Python implementations of common Unix commands for use when
native commands are not available (e.g., on Windows without Git Bash).
"""

import re
import shutil
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from src.platform.protocols.fallback import PythonCommandFallbackProtocol


class PythonCommandFallbackImpl:
    """
    Concrete implementation of Python command fallback protocol.

    Provides pure Python implementations of common Unix commands for
    cross-platform compatibility without external dependencies.

    No dependencies are injected since this is a pure utility class
    that only performs computations without side effects beyond
    file system operations.
    """

    def ls(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of ls command."""
        show_all = '-a' in args or '-la' in args or '-al' in args
        show_long = '-l' in args or '-la' in args or '-al' in args

        target = cwd
        for arg in args:
            if not arg.startswith('-'):
                target = cwd / arg
                break

        if not target.exists():
            return {
                'output': f'ls: {target}: No such file or directory',
                'returncode': 1,
                'used_fallback': True
            }

        if target.is_file():
            return {
                'output': str(target.name),
                'returncode': 0,
                'used_fallback': True
            }

        items = []
        for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
            if not show_all and item.name.startswith('.'):
                continue

            if show_long:
                stat = item.stat()
                size = stat.st_size
                mtime = stat.st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime('%b %d %H:%M')
                type_char = 'd' if item.is_dir() else '-'
                items.append(
                    f'{type_char}rw-r--r--  1 user  user  {size:>8} {date_str} {item.name}'
                )
            else:
                items.append(item.name)

        output = '\n'.join(items) if show_long else '  '.join(items)
        return {'output': output, 'returncode': 0, 'used_fallback': True}

    def cat(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of cat command."""
        if not args:
            return {
                'output': 'cat: missing file operand',
                'returncode': 1,
                'used_fallback': True
            }

        output_parts = []
        for arg in args:
            if arg.startswith('-'):
                continue
            filepath = cwd / arg
            if not filepath.exists():
                return {
                    'output': f'cat: {arg}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }
            try:
                output_parts.append(filepath.read_text(encoding='utf-8', errors='replace'))
            except Exception as e:
                return {
                    'output': f'cat: {arg}: {str(e)}',
                    'returncode': 1,
                    'used_fallback': True
                }

        return {'output': ''.join(output_parts), 'returncode': 0, 'used_fallback': True}

    def grep(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of grep command."""
        case_insensitive = '-i' in args
        show_line_numbers = '-n' in args
        recursive = '-r' in args or '-R' in args
        invert_match = '-v' in args

        pattern = None
        files = []
        for arg in args:
            if arg.startswith('-'):
                continue
            if pattern is None:
                pattern = arg
            else:
                files.append(arg)

        if pattern is None:
            return {
                'output': 'grep: missing pattern',
                'returncode': 1,
                'used_fallback': True
            }

        if not files:
            files = ['.']

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {
                'output': f'grep: invalid pattern: {str(e)}',
                'returncode': 1,
                'used_fallback': True
            }

        matches = []

        def search_file(filepath: Path, prefix: str = ''):
            try:
                lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()
                for i, line in enumerate(lines, 1):
                    match = regex.search(line)
                    if (match and not invert_match) or (not match and invert_match):
                        if show_line_numbers:
                            matches.append(f'{prefix}{filepath}:{i}:{line}')
                        elif prefix or len(files) > 1:
                            matches.append(f'{prefix}{filepath}:{line}')
                        else:
                            matches.append(line)
            except Exception:
                pass

        for file_arg in files:
            path = cwd / file_arg
            if path.is_file():
                search_file(path)
            elif path.is_dir() and recursive:
                for item in path.rglob('*'):
                    if item.is_file():
                        search_file(item, '')
            elif path.is_dir():
                return {
                    'output': f'grep: {file_arg}: Is a directory',
                    'returncode': 1,
                    'used_fallback': True
                }
            else:
                return {
                    'output': f'grep: {file_arg}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

        returncode = 0 if matches else 1
        return {'output': '\n'.join(matches), 'returncode': returncode, 'used_fallback': True}

    def find(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of find command."""
        search_path = cwd
        name_pattern = None
        type_filter = None

        i = 0
        while i < len(args):
            if args[i] == '-name' and i + 1 < len(args):
                name_pattern = args[i + 1]
                i += 2
            elif args[i] == '-type' and i + 1 < len(args):
                type_filter = args[i + 1]
                i += 2
            elif not args[i].startswith('-'):
                search_path = cwd / args[i]
                i += 1
            else:
                i += 1

        if not search_path.exists():
            return {
                'output': f'find: {search_path}: No such file or directory',
                'returncode': 1,
                'used_fallback': True
            }

        results = []

        def matches_pattern(name: str) -> bool:
            if name_pattern is None:
                return True
            regex_pattern = name_pattern.replace('.', r'\.').replace('*', '.*').replace('?', '.')
            return re.match(f'^{regex_pattern}$', name) is not None

        for item in search_path.rglob('*'):
            if type_filter == 'f' and not item.is_file():
                continue
            if type_filter == 'd' and not item.is_dir():
                continue
            if matches_pattern(item.name):
                results.append(str(item.relative_to(cwd)))

        return {'output': '\n'.join(sorted(results)), 'returncode': 0, 'used_fallback': True}

    def wc(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of wc command."""
        count_lines = '-l' in args
        count_words = '-w' in args
        count_chars = '-c' in args or '-m' in args

        if not any([count_lines, count_words, count_chars]):
            count_lines = count_words = count_chars = True

        files = [arg for arg in args if not arg.startswith('-')]

        if not files:
            return {
                'output': 'wc: missing file operand',
                'returncode': 1,
                'used_fallback': True
            }

        results = []
        total_lines = total_words = total_chars = 0

        for file_arg in files:
            filepath = cwd / file_arg
            if not filepath.exists():
                return {
                    'output': f'wc: {file_arg}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

            content = filepath.read_text(encoding='utf-8', errors='replace')
            lines = len(content.splitlines())
            words = len(content.split())
            chars = len(content)

            parts = []
            if count_lines:
                parts.append(f'{lines:>8}')
                total_lines += lines
            if count_words:
                parts.append(f'{words:>8}')
                total_words += words
            if count_chars:
                parts.append(f'{chars:>8}')
                total_chars += chars
            parts.append(file_arg)
            results.append(' '.join(parts))

        if len(files) > 1:
            parts = []
            if count_lines:
                parts.append(f'{total_lines:>8}')
            if count_words:
                parts.append(f'{total_words:>8}')
            if count_chars:
                parts.append(f'{total_chars:>8}')
            parts.append('total')
            results.append(' '.join(parts))

        return {'output': '\n'.join(results), 'returncode': 0, 'used_fallback': True}

    def head(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of head command."""
        num_lines = 10
        files = []

        i = 0
        while i < len(args):
            if args[i] == '-n' and i + 1 < len(args):
                num_lines = int(args[i + 1])
                i += 2
            elif args[i].startswith('-') and args[i][1:].isdigit():
                num_lines = int(args[i][1:])
                i += 1
            elif not args[i].startswith('-'):
                files.append(args[i])
                i += 1
            else:
                i += 1

        if not files:
            return {
                'output': 'head: missing file operand',
                'returncode': 1,
                'used_fallback': True
            }

        output_parts = []
        for filepath_str in files:
            filepath = cwd / filepath_str
            if not filepath.exists():
                return {
                    'output': f'head: {filepath_str}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

            lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()[:num_lines]
            if len(files) > 1:
                output_parts.append(f'==> {filepath_str} <==')
            output_parts.extend(lines)

        return {'output': '\n'.join(output_parts), 'returncode': 0, 'used_fallback': True}

    def tail(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of tail command."""
        num_lines = 10
        files = []

        i = 0
        while i < len(args):
            if args[i] == '-n' and i + 1 < len(args):
                num_lines = int(args[i + 1])
                i += 2
            elif args[i].startswith('-') and args[i][1:].isdigit():
                num_lines = int(args[i][1:])
                i += 1
            elif not args[i].startswith('-'):
                files.append(args[i])
                i += 1
            else:
                i += 1

        if not files:
            return {
                'output': 'tail: missing file operand',
                'returncode': 1,
                'used_fallback': True
            }

        output_parts = []
        for filepath_str in files:
            filepath = cwd / filepath_str
            if not filepath.exists():
                return {
                    'output': f'tail: {filepath_str}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

            lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()[-num_lines:]
            if len(files) > 1:
                output_parts.append(f'==> {filepath_str} <==')
            output_parts.extend(lines)

        return {'output': '\n'.join(output_parts), 'returncode': 0, 'used_fallback': True}

    def touch(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of touch command."""
        files = [arg for arg in args if not arg.startswith('-')]

        if not files:
            return {
                'output': 'touch: missing file operand',
                'returncode': 1,
                'used_fallback': True
            }

        for file_arg in files:
            filepath = cwd / file_arg
            filepath.touch()

        return {'output': '', 'returncode': 0, 'used_fallback': True}

    def mkdir_p(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of mkdir -p command."""
        dirs = [arg for arg in args if not arg.startswith('-')]

        if not dirs:
            return {
                'output': 'mkdir: missing operand',
                'returncode': 1,
                'used_fallback': True
            }

        for dir_arg in dirs:
            dirpath = cwd / dir_arg
            dirpath.mkdir(parents=True, exist_ok=True)

        return {'output': '', 'returncode': 0, 'used_fallback': True}

    def rm(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of rm command."""
        recursive = '-r' in args or '-rf' in args or '-R' in args
        force = '-f' in args or '-rf' in args

        files = [arg for arg in args if not arg.startswith('-')]

        if not files:
            return {
                'output': 'rm: missing operand',
                'returncode': 1,
                'used_fallback': True
            }

        for file_arg in files:
            filepath = cwd / file_arg
            if not filepath.exists():
                if not force:
                    return {
                        'output': f'rm: {file_arg}: No such file or directory',
                        'returncode': 1,
                        'used_fallback': True
                    }
                continue

            if filepath.is_dir():
                if not recursive:
                    return {
                        'output': f'rm: {file_arg}: is a directory',
                        'returncode': 1,
                        'used_fallback': True
                    }
                shutil.rmtree(filepath)
            else:
                filepath.unlink()

        return {'output': '', 'returncode': 0, 'used_fallback': True}

    def cp(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of cp command."""
        recursive = '-r' in args or '-R' in args

        files = [arg for arg in args if not arg.startswith('-')]

        if len(files) < 2:
            return {
                'output': 'cp: missing destination operand',
                'returncode': 1,
                'used_fallback': True
            }

        *sources, dest = files
        dest_path = cwd / dest

        for src_arg in sources:
            src_path = cwd / src_arg
            if not src_path.exists():
                return {
                    'output': f'cp: {src_arg}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

            if src_path.is_dir():
                if not recursive:
                    return {
                        'output': f'cp: -r not specified; omitting directory {src_arg}',
                        'returncode': 1,
                        'used_fallback': True
                    }
                if dest_path.exists() and dest_path.is_dir():
                    shutil.copytree(src_path, dest_path / src_path.name)
                else:
                    shutil.copytree(src_path, dest_path)
            else:
                if dest_path.is_dir():
                    shutil.copy2(src_path, dest_path / src_path.name)
                else:
                    shutil.copy2(src_path, dest_path)

        return {'output': '', 'returncode': 0, 'used_fallback': True}

    def mv(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of mv command."""
        files = [arg for arg in args if not arg.startswith('-')]

        if len(files) < 2:
            return {
                'output': 'mv: missing destination operand',
                'returncode': 1,
                'used_fallback': True
            }

        *sources, dest = files
        dest_path = cwd / dest

        for src_arg in sources:
            src_path = cwd / src_arg
            if not src_path.exists():
                return {
                    'output': f'mv: {src_arg}: No such file or directory',
                    'returncode': 1,
                    'used_fallback': True
                }

            if dest_path.is_dir():
                shutil.move(str(src_path), str(dest_path / src_path.name))
            else:
                shutil.move(str(src_path), str(dest_path))

        return {'output': '', 'returncode': 0, 'used_fallback': True}

    def which(self, args: List[str]) -> Dict[str, Any]:
        """Python implementation of which command."""
        if not args:
            return {
                'output': 'which: missing argument',
                'returncode': 1,
                'used_fallback': True
            }

        results = []
        not_found = False
        for cmd in args:
            if cmd.startswith('-'):
                continue
            path = shutil.which(cmd)
            if path:
                results.append(path)
            else:
                results.append(f'{cmd} not found')
                not_found = True

        return {
            'output': '\n'.join(results),
            'returncode': 1 if not_found else 0,
            'used_fallback': True
        }

    def pwd(self, cwd: Path) -> Dict[str, Any]:
        """Python implementation of pwd command."""
        return {
            'output': str(cwd.resolve()),
            'returncode': 0,
            'used_fallback': True
        }
