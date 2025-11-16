"""
Configuration for CodeAgent.

Centralizes all magic numbers and configurable values.
"""

from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class AgentConfig:
    """Configuration settings for CodeAgent."""

    # File operations
    max_file_read_size: int = 10000
    max_file_listing: int = 100
    max_directory_tree_lines: int = 200

    # Command execution
    command_timeout: int = 300  # 5 minutes for long-running commands
    max_command_output: int = 10000
    dangerous_commands: List[str] = field(
        default_factory=lambda: ['rm -rf', 'del /f', 'format', 'mkfs', '> /dev/', 'sudo']
    )
    # Commands known to be long-running (pattern matches)
    long_running_commands: List[str] = field(
        default_factory=lambda: [
            'create-react-app', 'npm install', 'pip install', 'cargo build',
            'docker build', 'npm run build', 'yarn install', 'pnpm install'
        ]
    )
    # Commands that may prompt for input (should warn user)
    interactive_commands: List[str] = field(
        default_factory=lambda: [
            # Package managers - init/create commands
            'npm init', 'npm create', 'npx ', 'yarn init', 'yarn create',
            'pnpm init', 'pnpm create', 'pnpm dlx', 'bun init', 'bun create', 'bunx ',
            'poetry init', 'poetry new', 'pipenv --python',
            'cargo init', 'cargo new', 'go mod init',
            # Project scaffolding tools (these prompt for options)
            'create-vite', 'create-next', 'create-nuxt', 'create-vue',
            'vite@', 'next@', 'nuxt@',  # npm create vite@latest, etc.
            'vue create', 'ng new', 'rails new', 'expo init',
            'django-admin startproject', 'cookiecutter',
            # Version control (interactive modes)
            'git commit', 'git rebase -i', 'git merge', 'git stash',
            'git add -p', 'git checkout -p', 'git reset -p',
            # System/Auth (require password or confirmation)
            'ssh ', 'scp ', 'sftp ', 'sudo ', 'passwd', 'su ',
            # Database clients (open interactive shells)
            'mysql ', 'psql ', 'mongo ', 'mongosh', 'redis-cli', 'sqlite3 ',
            # Installers that may prompt
            'apt install', 'apt-get install', 'dnf install', 'yum install',
            'brew install', 'choco install', 'winget install', 'scoop install',
            # Cloud/Deploy (login flows, config wizards)
            'aws configure', 'gcloud init', 'gcloud auth', 'az login',
            'heroku login', 'vercel login', 'netlify login', 'firebase login',
            'docker login', 'gh auth login'
        ]
    )

    # Code search
    max_search_results: int = 50

    # Git operations
    git_timeout: int = 10
    git_diff_timeout: int = 30
    max_git_diff_size: int = 5000
    max_git_blame_size: int = 5000
    max_git_show_size: int = 5000
    max_recent_changes_size: int = 15000
    max_recent_commits: int = 10

    # Directory traversal
    skip_directories: Set[str] = field(
        default_factory=lambda: {
            '.git', '__pycache__', 'node_modules', '.venv',
            'venv', 'env', '.tox', '.pytest_cache'
        }
    )
    allowed_hidden_files: Set[str] = field(
        default_factory=lambda: {'.env', '.gitignore'}
    )

    # Display/UI
    audit_log_result_truncation: int = 500
    result_display_truncation: int = 300
    write_preview_truncation: int = 500

    # LLM settings
    default_max_tokens: int = 1500
    default_temperature: float = 0.3

    # Provider preferences (first available will be used)
    planner_preferences: List[str] = field(
        default_factory=lambda: ['gemini', 'groq']
    )
    executor_preferences: List[str] = field(
        default_factory=lambda: ['cerebras']
    )

    # Completion validation
    meaningful_actions: List[str] = field(
        default_factory=lambda: ['write_file', 'run_command']
    )
