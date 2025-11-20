"""
Infrastructure protocols.

Defines abstract interfaces for external dependencies and infrastructure concerns.
These protocols enable dependency injection and testing without real I/O operations.
"""

from typing import Protocol, Dict, Any, Optional, List, BinaryIO
from pathlib import Path


class FileSystemProtocol(Protocol):
    """
    Protocol for file system operations.

    Abstracts file system I/O to enable testing without real file operations.
    Provides methods for reading, writing, listing, and managing files and directories.

    Implementations:
    - RealFileSystem: Uses actual file system via pathlib.Path
    - InMemoryFileSystem: Stores files in memory for testing
    - MockFileSystem: Configurable mock for specific test scenarios

    Example:
        def save_data(fs: FileSystemProtocol, path: str, data: str) -> None:
            fs.write_text(path, data)

        # In production
        save_data(RealFileSystem(), "output.txt", "hello")

        # In tests
        save_data(InMemoryFileSystem(), "output.txt", "hello")
    """

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """
        Read file contents as text.

        Args:
            path: File path to read
            encoding: Text encoding (default: utf-8)

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If no read permission
        """
        ...

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """
        Write text content to file.

        Args:
            path: File path to write
            content: Text content to write
            encoding: Text encoding (default: utf-8)

        Raises:
            PermissionError: If no write permission
        """
        ...

    def read_bytes(self, path: str) -> bytes:
        """
        Read file contents as bytes.

        Args:
            path: File path to read

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If no read permission
        """
        ...

    def write_bytes(self, path: str, content: bytes) -> None:
        """
        Write binary content to file.

        Args:
            path: File path to write
            content: Binary content to write

        Raises:
            PermissionError: If no write permission
        """
        ...

    def exists(self, path: str) -> bool:
        """
        Check if path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        ...

    def is_file(self, path: str) -> bool:
        """
        Check if path is a file.

        Args:
            path: Path to check

        Returns:
            True if path is a file, False otherwise
        """
        ...

    def is_dir(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory, False otherwise
        """
        ...

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """
        Create directory.

        Args:
            path: Directory path to create
            parents: Create parent directories if needed
            exist_ok: Don't raise error if directory exists

        Raises:
            FileExistsError: If directory exists and exist_ok=False
            PermissionError: If no write permission
        """
        ...

    def list_dir(self, path: str) -> List[str]:
        """
        List directory contents.

        Args:
            path: Directory path to list

        Returns:
            List of file/directory names (not full paths)

        Raises:
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path is not a directory
        """
        ...

    def glob(self, pattern: str) -> List[str]:
        """
        Find files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py")

        Returns:
            List of matching file paths
        """
        ...

    def delete(self, path: str) -> None:
        """
        Delete file or empty directory.

        Args:
            path: Path to delete

        Raises:
            FileNotFoundError: If path doesn't exist
            PermissionError: If no delete permission
            OSError: If directory is not empty
        """
        ...

    def delete_tree(self, path: str) -> None:
        """
        Recursively delete directory and contents.

        Args:
            path: Directory path to delete

        Raises:
            FileNotFoundError: If path doesn't exist
            PermissionError: If no delete permission
        """
        ...

    def resolve(self, path: str) -> str:
        """
        Resolve path to absolute path.

        Args:
            path: Path to resolve

        Returns:
            Absolute path string
        """
        ...


class HTTPClientProtocol(Protocol):
    """
    Protocol for HTTP client operations.

    Abstracts HTTP requests to enable testing without real network calls.
    Provides methods for GET, POST, and generic request operations.

    Implementations:
    - RequestsHTTPClient: Uses requests library for real HTTP calls
    - MockHTTPClient: Returns preset responses for testing
    - RecordingHTTPClient: Records requests for verification

    Example:
        def fetch_data(client: HTTPClientProtocol, url: str) -> Dict[str, Any]:
            response = client.get(url, headers={"Accept": "application/json"})
            return response["data"]

        # In production
        fetch_data(RequestsHTTPClient(), "https://api.example.com/data")

        # In tests
        mock = MockHTTPClient(responses={"https://api.example.com/data": {"data": "test"}})
        fetch_data(mock, "https://api.example.com/data")
    """

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Perform HTTP GET request.

        Args:
            url: URL to request
            headers: Optional HTTP headers
            params: Optional query parameters
            timeout: Optional timeout in seconds

        Returns:
            Response data as dictionary

        Raises:
            HTTPError: If request fails
            TimeoutError: If request times out
        """
        ...

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Perform HTTP POST request.

        Args:
            url: URL to request
            data: Optional form data
            json: Optional JSON body
            headers: Optional HTTP headers
            timeout: Optional timeout in seconds

        Returns:
            Response data as dictionary

        Raises:
            HTTPError: If request fails
            TimeoutError: If request times out
        """
        ...

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Perform generic HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: URL to request
            headers: Optional HTTP headers
            data: Optional request body
            timeout: Optional timeout in seconds
            **kwargs: Additional request parameters

        Returns:
            Response data as dictionary

        Raises:
            HTTPError: If request fails
            TimeoutError: If request times out
        """
        ...


class EnvironmentProtocol(Protocol):
    """
    Protocol for environment variable access.

    Abstracts environment variable operations to enable testing with
    controlled configurations without modifying actual environment.

    Implementations:
    - OSEnvironment: Reads from actual os.environ
    - TestEnvironment: Uses in-memory dictionary for testing
    - PrefixedEnvironment: Wraps another environment with key prefix

    Example:
        def get_api_key(env: EnvironmentProtocol) -> str:
            key = env.get("API_KEY")
            if not key:
                raise ValueError("API_KEY not set")
            return key

        # In production
        get_api_key(OSEnvironment())

        # In tests
        test_env = TestEnvironment({"API_KEY": "test-key-123"})
        get_api_key(test_env)
    """

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get environment variable value.

        Args:
            key: Environment variable name
            default: Default value if not found

        Returns:
            Environment variable value or default
        """
        ...

    def set(self, key: str, value: str) -> None:
        """
        Set environment variable value.

        Args:
            key: Environment variable name
            value: Value to set
        """
        ...

    def delete(self, key: str) -> None:
        """
        Delete environment variable.

        Args:
            key: Environment variable name to delete

        Raises:
            KeyError: If key doesn't exist
        """
        ...

    def get_all(self) -> Dict[str, str]:
        """
        Get all environment variables.

        Returns:
            Dictionary of all environment variables
        """
        ...

    def exists(self, key: str) -> bool:
        """
        Check if environment variable exists.

        Args:
            key: Environment variable name

        Returns:
            True if variable exists, False otherwise
        """
        ...


class ConfigLoaderProtocol(Protocol):
    """
    Protocol for configuration loading and management.

    Abstracts configuration operations to enable testing with
    controlled configurations without file I/O.

    Implementations:
    - JSONConfigLoader: Loads config from JSON files
    - YAMLConfigLoader: Loads config from YAML files
    - StaticConfig: Uses fixed in-memory configuration
    - ChainedConfig: Combines multiple config sources with priority

    Example:
        def init_app(config: ConfigLoaderProtocol) -> None:
            db_url = config.get("database.url")
            timeout = config.get("timeout", 30)

        # In production
        init_app(JSONConfigLoader("config.json"))

        # In tests
        init_app(StaticConfig({"database.url": "sqlite:///:memory:", "timeout": 5}))
    """

    def load(self, source: Optional[str] = None) -> None:
        """
        Load configuration from source.

        Args:
            source: Configuration source (file path, URL, etc.)
                   None to reload from current source

        Raises:
            FileNotFoundError: If source file doesn't exist
            ValueError: If configuration is invalid
        """
        ...

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Get configuration value.

        Supports dot notation for nested keys (e.g., "database.host").

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        ...

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Supports dot notation for nested keys.

        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        ...

    def save(self, destination: Optional[str] = None) -> None:
        """
        Save configuration to destination.

        Args:
            destination: Save destination (file path, URL, etc.)
                        None to save to current source

        Raises:
            PermissionError: If no write permission
        """
        ...

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration as dictionary.

        Returns:
            Complete configuration dictionary
        """
        ...

    def reload(self) -> None:
        """
        Reload configuration from source.

        Raises:
            FileNotFoundError: If source no longer exists
            ValueError: If configuration is invalid
        """
        ...
