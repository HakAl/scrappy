"""
Session persistence for orchestrator state.

Handles saving and loading of session data including working memory and conversation history.
"""

from datetime import datetime
from pathlib import Path
import json

from .memory import WorkingMemory


class SessionManager:
    """
    Manages session persistence for the orchestrator.

    Features:
    - Save/load working memory
    - Save/load conversation history
    - Save/load task history
    - Session metadata
    """

    def __init__(self, project_path: Path):
        """
        Initialize session manager.

        Args:
            project_path: Path to project directory
        """
        self.project_path = project_path
        self.session_file = project_path / ".llm_team_session.json"

    def save_session(
        self,
        working_memory: WorkingMemory,
        task_history: list,
        session_start: datetime,
        conversation_history: list = None
    ) -> str:
        """
        Save current session to disk.

        Args:
            working_memory: WorkingMemory instance to save
            task_history: List of task history entries
            session_start: When the session started
            conversation_history: Optional list of conversation messages

        Returns:
            Path to saved session file

        Raises:
            RuntimeError: If save fails
        """
        session_data = {
            **working_memory.to_dict(),
            'conversation_history': conversation_history or [],
            'saved_at': datetime.now().isoformat(),
            'session_start': session_start.isoformat(),
            'task_history': task_history,
        }

        try:
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
            return str(self.session_file)
        except Exception as e:
            raise RuntimeError(f"Failed to save session: {e}")

    def load_session(self) -> dict:
        """
        Load previous session from disk.

        Returns:
            Dict with:
            - status: 'loaded', 'no_session', or 'error'
            - working_memory: WorkingMemory instance (if loaded)
            - task_history: List of task history (if loaded)
            - conversation_history: List of messages (if loaded)
            - Various statistics
        """
        if not self.session_file.exists():
            return {'status': 'no_session', 'message': 'No previous session found'}

        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore working memory
            working_memory = WorkingMemory.from_dict(data)

            # Get task history
            task_history = data.get('task_history', [])

            # Get conversation history
            conversation_history = data.get('conversation_history', [])

            return {
                'status': 'loaded',
                'working_memory': working_memory,
                'task_history': task_history,
                'conversation_history': conversation_history,
                'saved_at': data.get('saved_at', 'unknown'),
                'session_start': data.get('session_start', 'unknown'),
                'files_restored': len(working_memory.file_reads),
                'searches_restored': len(working_memory.search_results),
                'git_ops_restored': len(working_memory.git_operations),
                'discoveries_restored': len(working_memory.discoveries),
                'tasks_restored': len(task_history),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def clear_session(self):
        """Delete saved session file."""
        if self.session_file.exists():
            self.session_file.unlink()

    def has_session(self) -> bool:
        """Check if a saved session exists."""
        return self.session_file.exists()

    def get_session_info(self) -> dict:
        """
        Get information about saved session without loading it.

        Returns:
            Dict with session metadata
        """
        if not self.session_file.exists():
            return {'exists': False}

        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return {
                'exists': True,
                'saved_at': data.get('saved_at', 'unknown'),
                'session_start': data.get('session_start', 'unknown'),
                'file_count': len(data.get('file_reads', {})),
                'search_count': len(data.get('search_results', [])),
                'discovery_count': len(data.get('discoveries', [])),
                'task_count': len(data.get('task_history', [])),
                'has_conversation': len(data.get('conversation_history', [])) > 0,
            }
        except Exception:
            return {'exists': True, 'error': 'Could not read session file'}
