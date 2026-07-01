"""
Project type and language detection for codebase analysis.

Detects project markers (package.json, requirements.txt, etc.) and determines
project types, programming languages, and sub-project structure.
"""

from pathlib import Path


class ProjectDetector:
    """
    Detects project types and languages from file markers and extensions.

    Usage:
        detector = ProjectDetector("/path/to/project")
        detector.set_file_index(file_index)  # From FileScanner

        markers = detector.detect_markers()
        project_type = detector.get_project_type()
        languages = detector.get_languages()
    """

    def __init__(self, project_path):
        """
        Initialize the project detector.

        Args:
            project_path: Path to project root (string or Path)
        """
        if isinstance(project_path, str):
            self.project_path = Path(project_path)
        else:
            self.project_path = project_path

        self._file_index = {}
        self._markers_cache = None

    def set_file_index(self, file_index: dict):
        """
        Set the file index for marker detection.

        Args:
            file_index: Dict mapping categories to file lists from FileScanner
        """
        self._file_index = file_index if file_index else {}
        self._markers_cache = None  # Clear cache when file_index changes

    def detect_markers(self) -> dict:
        """
        Detect all project marker files.

        Returns:
            Dict with has_* boolean flags for each marker type
        """
        if self._markers_cache is not None:
            return self._markers_cache

        # Build list of all files for marker detection
        all_files = []
        for file_list in self._file_index.values():
            all_files.extend(file_list)

        # Helper to check if marker exists anywhere in tree
        def has_marker(marker_name):
            return any(
                f.endswith(marker_name) or f == marker_name
                for f in all_files
            )

        # Helper to check if marker exists in root only
        def has_root_marker(marker_name):
            return marker_name in all_files

        markers = {
            'has_readme': has_root_marker('README.md') or has_root_marker('README'),
            'has_requirements': has_marker('requirements.txt'),
            'has_package_json': has_marker('package.json'),
            'has_pyproject': has_marker('pyproject.toml'),
            'has_git': (self.project_path / '.git').exists(),
            'has_pom_xml': has_marker('pom.xml'),
            'has_build_gradle': has_marker('build.gradle') or has_marker('build.gradle.kts'),
            'has_cargo_toml': has_marker('Cargo.toml'),
            'has_go_mod': has_marker('go.mod'),
            'has_gemfile': has_marker('Gemfile'),
            'has_csproj': any(
                f.endswith('.csproj') or f.endswith('.sln')
                for f in all_files
            ),
        }

        self._markers_cache = markers
        return markers

    def get_project_type(self) -> str:
        """
        Determine the primary project type based on detected markers.

        Returns:
            String identifier for project type (e.g., 'python', 'java', 'nodejs')
        """
        markers = self.detect_markers()

        # Priority order for project type detection
        if markers.get('has_requirements') or markers.get('has_pyproject'):
            return 'python'
        elif markers.get('has_pom_xml'):
            return 'java'
        elif markers.get('has_build_gradle'):
            return 'java'
        elif markers.get('has_package_json'):
            return 'nodejs'
        elif markers.get('has_cargo_toml'):
            return 'rust'
        elif markers.get('has_go_mod'):
            return 'go'
        elif markers.get('has_gemfile'):
            return 'ruby'
        elif markers.get('has_csproj'):
            return 'dotnet'
        else:
            return 'unknown'

    def get_languages(self) -> list:
        """
        Get list of programming languages used in the codebase.

        Returns:
            List of language names based on file extensions found
        """
        languages = []

        if self._file_index.get('python'):
            languages.append('python')

        js_files = self._file_index.get('javascript', [])
        if js_files:
            # Check if any are TypeScript
            has_ts = any(
                f.endswith('.ts') or f.endswith('.tsx')
                for f in js_files
            )
            has_js = any(
                f.endswith('.js') or f.endswith('.jsx')
                for f in js_files
            )

            if has_ts:
                languages.append('typescript')
            if has_js:
                languages.append('javascript')
            # If no explicit .js/.ts but files exist, default to javascript
            if not has_ts and not has_js and js_files:
                languages.append('javascript')

        return languages

    def get_language_stats(self) -> dict:
        """
        Get count of files per programming language.

        Returns:
            Dict mapping language name to file count
        """
        return {k: len(v) for k, v in self._file_index.items() if v}

    def get_primary_language(self) -> str:
        """
        Determine primary language based on file count.

        Returns:
            Language with most files, or 'unknown' if no code files
        """
        stats = self.get_language_stats()

        # Only consider actual code languages
        code_languages = {
            k: v for k, v in stats.items()
            if k in ('python', 'javascript') and v > 0
        }

        if not code_languages:
            return 'unknown'

        return max(code_languages.items(), key=lambda x: x[1])[0]

    def find_project_markers(self) -> list:
        """
        Find all project marker files (package.json, requirements.txt, etc.) anywhere in tree.

        Returns:
            List of relative paths to project marker files
        """
        marker_names = {
            'package.json', 'requirements.txt', 'pyproject.toml', 'setup.py',
            'pom.xml', 'build.gradle', 'build.gradle.kts',
            'Cargo.toml', 'go.mod', 'Gemfile', 'composer.json'
        }

        markers = []

        # Check config category
        for file_path in self._file_index.get('config', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        # Check other category for markers not in config
        for file_path in self._file_index.get('other', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        # Check docs category (requirements.txt has .txt extension)
        for file_path in self._file_index.get('docs', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        return markers

    def get_marker_locations(self) -> dict:
        """
        Map directories to their project marker files.

        Returns:
            Dict mapping directory path to marker filename
        """
        markers = self.find_project_markers()
        locations = {}

        for marker_path in markers:
            # Normalize path separators
            normalized = marker_path.replace('\\', '/')

            # Get directory containing the marker
            if '/' in normalized:
                parts = normalized.rsplit('/', 1)
                directory = parts[0]
                marker_name = parts[1]
            else:
                # Marker in root directory
                directory = '.'
                marker_name = marker_path

            locations[directory] = marker_name

        return locations

    def get_sub_projects(self) -> dict:
        """
        Detect project types in subdirectories (for monorepos).

        Returns:
            Dict mapping subdirectory name to project type
        """
        marker_locations = self.get_marker_locations()
        sub_projects = {}

        # Map marker files to project types
        marker_to_type = {
            'package.json': 'nodejs',
            'requirements.txt': 'python',
            'pyproject.toml': 'python',
            'setup.py': 'python',
            'pom.xml': 'java',
            'build.gradle': 'java',
            'build.gradle.kts': 'java',
            'Cargo.toml': 'rust',
            'go.mod': 'go',
            'Gemfile': 'ruby',
            'composer.json': 'php',
        }

        for directory, marker in marker_locations.items():
            if directory != '.':  # Skip root
                project_type = marker_to_type.get(marker, 'unknown')
                # Use the top-level directory name as key
                top_dir = directory.split('/')[0] if '/' in directory else directory
                # If we already have this directory, keep the first one found
                if top_dir not in sub_projects:
                    sub_projects[top_dir] = project_type
                # For nested paths like services/auth-api, also track the full path
                if '/' in directory:
                    sub_projects[directory] = project_type

        return sub_projects
