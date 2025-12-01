"""Direct command classification strategy."""

from typing import List

from ..classification_strategy import PatternBasedStrategy, TaskType


class DirectCommandStrategy(PatternBasedStrategy):
    """
    Strategy for identifying direct shell commands.

    Matches commands that can be executed directly without AI reasoning,
    such as package managers, git, docker, build tools, etc.
    """

    def task_type(self) -> TaskType:
        """Return DIRECT_COMMAND task type."""
        return TaskType.DIRECT_COMMAND

    def _init_patterns(self) -> None:
        """Initialize direct command patterns."""
        # Package managers
        self.add_patterns([
            (r'^(pip|pip3)\s+(install|uninstall|freeze|list|show)', 1.0, "pip_command"),
            (r'^npx\s+', 1.0, "npx_command"),
            (r'^(npm|yarn|pnpm)\s+(install|add|remove|run|build|test|start)', 1.0, "npm_command"),
            (r'^(cargo|rustup)\s+(install|build|run|test|add|remove)', 1.0, "cargo_command"),
            (r'^(gem|bundle)\s+(install|exec|update)', 1.0, "gem_command"),
            (r'^(go)\s+(get|build|run|test|mod)', 1.0, "go_command"),
        ])

        # Git commands
        self.add_patterns([
            (r'^git\s+(status|log|diff|branch|checkout|pull|push|add|commit|stash)', 1.0, "git_command"),
            (r'^git\s+\S+', 0.9, "git_generic"),
        ])

        # System commands
        self.add_patterns([
            (r'^(ls|dir|pwd|cd|mkdir|rmdir|rm|cp|mv|touch|cat|head|tail)\s*', 0.95, "filesystem_command"),
            (r'^(docker|docker-compose|podman)\s+\S+', 1.0, "docker_command"),
            (r'^(kubectl|k8s|helm)\s+\S+', 1.0, "kubernetes_command"),
            (r'^(python|python3|node|ruby|java|javac)\s+\S+', 0.9, "interpreter_command"),
        ])

        # Build/test commands
        self.add_patterns([
            (r'^(make|cmake|gradle|mvn)(?!\s+a\s)\s*', 1.0, "build_command"),
            (r'^pytest\s*', 1.0, "test_command"),
            (r'^(tox|nox|coverage)\s*', 1.0, "test_command"),
        ])

        # Direct command request patterns
        self.add_patterns([
            (r'^run\s+(pip|npm|git|docker|pytest|make)\s+', 0.95, "run_explicit"),
            (r'^execute\s+', 0.9, "execute_explicit"),
            (r'^install\s+(\S+)', 0.85, "install_request"),
            (r'^(start|stop|restart)\s+\S+', 0.8, "service_control"),
        ])

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate reasoning for direct command classification."""
        if not patterns:
            return ""
        pattern_str = ", ".join(patterns[:3])
        return f"Detected direct command patterns: {pattern_str}"
