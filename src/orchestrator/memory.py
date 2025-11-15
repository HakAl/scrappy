"""
Working memory management for orchestrator sessions.

Provides ephemeral storage for file reads, searches, and discoveries during a session.
"""

from datetime import datetime


class WorkingMemory:
    """
    Session-scoped working memory for the orchestrator.

    Tracks:
    - Recent file reads (LRU cache)
    - Search results
    - Git operations
    - Key discoveries/learnings
    """

    def __init__(
        self,
        max_file_cache: int = 20,
        max_searches: int = 10,
        max_git_ops: int = 10
    ):
        """
        Initialize working memory.

        Args:
            max_file_cache: Maximum number of files to cache
            max_searches: Maximum number of search results to keep
            max_git_ops: Maximum number of git operations to track
        """
        self.file_reads: dict = {}  # path -> {'content': str, 'timestamp': datetime, 'lines': int}
        self.search_results: list = []  # list of {'query': str, 'results': list, 'timestamp': datetime}
        self.git_operations: list = []  # list of {'operation': str, 'output': str, 'timestamp': datetime}
        self.discoveries: list = []  # list of {'finding': str, 'location': str, 'timestamp': datetime}

        self.max_file_cache = max_file_cache
        self.max_searches = max_searches
        self.max_git_ops = max_git_ops

    def remember_file_read(self, path: str, content: str, lines: int = 0):
        """
        Store a file read in working memory (LRU cache).

        Args:
            path: File path
            content: File content
            lines: Number of lines in file
        """
        self.file_reads[path] = {
            'content': content,
            'timestamp': datetime.now(),
            'lines': lines
        }
        # Enforce LRU cache size
        if len(self.file_reads) > self.max_file_cache:
            # Remove oldest entry
            oldest_path = min(
                self.file_reads.keys(),
                key=lambda p: self.file_reads[p]['timestamp']
            )
            del self.file_reads[oldest_path]

    def remember_search(self, query: str, results: list):
        """
        Store a search result in working memory.

        Args:
            query: Search query
            results: Search results
        """
        self.search_results.append({
            'query': query,
            'results': results,
            'timestamp': datetime.now()
        })
        # Keep only last N searches
        if len(self.search_results) > self.max_searches:
            self.search_results = self.search_results[-self.max_searches:]

    def remember_git_operation(self, operation: str, output: str):
        """
        Store a git operation result in working memory.

        Args:
            operation: Git command executed
            output: Command output
        """
        self.git_operations.append({
            'operation': operation,
            'output': output,
            'timestamp': datetime.now()
        })
        # Keep only last N operations
        if len(self.git_operations) > self.max_git_ops:
            self.git_operations = self.git_operations[-self.max_git_ops:]

    def add_discovery(self, finding: str, location: str = ""):
        """
        Add a discovery/learning to working memory.

        Args:
            finding: What was discovered
            location: Where it was found (optional)
        """
        self.discoveries.append({
            'finding': finding,
            'location': location,
            'timestamp': datetime.now()
        })

    def get_summary(self) -> dict:
        """Get a summary of current working memory state."""
        return {
            'files_cached': len(self.file_reads),
            'cached_files': list(self.file_reads.keys()),
            'recent_searches': len(self.search_results),
            'git_operations': len(self.git_operations),
            'discoveries': len(self.discoveries),
        }

    def get_context_string(self) -> str:
        """Build context string from working memory for LLM augmentation."""
        parts = []

        # Recent file reads (just paths and line counts, not full content)
        if self.file_reads:
            files_info = []
            for path, info in self.file_reads.items():
                files_info.append(f"  - {path} ({info['lines']} lines)")
            parts.append("Recently accessed files:\n" + "\n".join(files_info))

        # Recent searches
        if self.search_results:
            searches_info = []
            for search in self.search_results[-3:]:  # Last 3 searches
                result_count = len(search['results']) if isinstance(search['results'], list) else 0
                searches_info.append(f"  - '{search['query']}' ({result_count} results)")
            parts.append("Recent searches:\n" + "\n".join(searches_info))

        # Recent git operations
        if self.git_operations:
            git_info = []
            for op in self.git_operations[-3:]:  # Last 3 ops
                git_info.append(f"  - {op['operation']}")
            parts.append("Recent git operations:\n" + "\n".join(git_info))

        # Discoveries
        if self.discoveries:
            disc_info = []
            for disc in self.discoveries[-5:]:  # Last 5 discoveries
                loc = f" at {disc['location']}" if disc['location'] else ""
                disc_info.append(f"  - {disc['finding']}{loc}")
            parts.append("Key discoveries:\n" + "\n".join(disc_info))

        if parts:
            return "[Session Working Memory]\n" + "\n\n".join(parts)
        return ""

    def clear(self):
        """Clear all working memory."""
        self.file_reads = {}
        self.search_results = []
        self.git_operations = []
        self.discoveries = []

    def to_dict(self) -> dict:
        """
        Serialize working memory to a dictionary for persistence.

        Returns:
            Dict with all memory data (timestamps as ISO strings)
        """
        data = {
            'file_reads': {},
            'search_results': [],
            'git_operations': [],
            'discoveries': [],
        }

        # Serialize file reads
        for path, info in self.file_reads.items():
            data['file_reads'][path] = {
                'content': info['content'],
                'timestamp': info['timestamp'].isoformat(),
                'lines': info['lines']
            }

        # Serialize search results
        for search in self.search_results:
            data['search_results'].append({
                'query': search['query'],
                'results': search['results'],
                'timestamp': search['timestamp'].isoformat()
            })

        # Serialize git operations
        for op in self.git_operations:
            data['git_operations'].append({
                'operation': op['operation'],
                'output': op['output'],
                'timestamp': op['timestamp'].isoformat()
            })

        # Serialize discoveries
        for disc in self.discoveries:
            data['discoveries'].append({
                'finding': disc['finding'],
                'location': disc['location'],
                'timestamp': disc['timestamp'].isoformat()
            })

        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkingMemory':
        """
        Deserialize working memory from a dictionary.

        Args:
            data: Dict with serialized memory data

        Returns:
            WorkingMemory instance
        """
        memory = cls()

        # Restore file reads
        for path, info in data.get('file_reads', {}).items():
            memory.file_reads[path] = {
                'content': info['content'],
                'timestamp': datetime.fromisoformat(info['timestamp']),
                'lines': info['lines']
            }

        # Restore search results
        for search in data.get('search_results', []):
            memory.search_results.append({
                'query': search['query'],
                'results': search['results'],
                'timestamp': datetime.fromisoformat(search['timestamp'])
            })

        # Restore git operations
        for op in data.get('git_operations', []):
            memory.git_operations.append({
                'operation': op['operation'],
                'output': op['output'],
                'timestamp': datetime.fromisoformat(op['timestamp'])
            })

        # Restore discoveries
        for disc in data.get('discoveries', []):
            memory.discoveries.append({
                'finding': disc['finding'],
                'location': disc['location'],
                'timestamp': datetime.fromisoformat(disc['timestamp'])
            })

        return memory
