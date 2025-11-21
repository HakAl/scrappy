#!/usr/bin/env python3
"""
Standalone test script for background semantic search initialization.

This script uses the same import pattern as the user's working scripts:
it adds the project root to sys.path and imports from 'src'.
"""

import os
import sys
import time
import tempfile
import shutil
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.context.semantic.initializer import SemanticSearchInitializer
from src.context.code_chunker import SemanticCodeChunker


def create_test_files(test_dir):
    """Create some test Python files for indexing."""
    test_files = {}

    # File 1: Simple function
    file1_path = test_dir / "utils.py"
    file1_content = """
def calculate_sum(a, b):
    \"\"\"Calculate the sum of two numbers.\"\"\"
    return a + b

def calculate_product(a, b):
    \"\"\"Calculate the product of two numbers.\"\"\"
    return a * b
"""
    file1_path.write_text(file1_content)
    test_files[str(file1_path)] = file1_content

    # File 2: Class definition
    file2_path = test_dir / "models.py"
    file2_content = """
class User:
    \"\"\"User model class.\"\"\"

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def get_display_name(self):
        return self.username

    def __str__(self):
        return f"User(username={self.username}, email={self.email})"
"""
    file2_path.write_text(file2_content)
    test_files[str(file2_path)] = file2_content

    # File 3: More complex code
    file3_path = test_dir / "api.py"
    file3_content = """
import requests
from typing import Dict, Any, Optional

class APIClient:
    \"\"\"Simple API client for making HTTP requests.\"\"\"

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        \"\"\"Make a GET request to the API.\"\"\"
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def post(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        \"\"\"Make a POST request to the API.\"\"\"
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
"""
    file3_path.write_text(file3_content)
    test_files[str(file3_path)] = file3_content

    return test_files


def print_status(initializer):
    """Print the current status of the initializer."""
    status = initializer.get_status()
    print(f"[{time.strftime('%H:%M:%S')}] Status: {status}")


def monitor_initialization(initializer, interval=2):
    """Monitor the initialization process and print status updates."""
    while not initializer.is_complete():
        print_status(initializer)
        time.sleep(interval)

    # Final status
    print_status(initializer)


def test_semantic_search(search_provider, test_files):
    """Test the semantic search functionality."""
    print("\n=== Testing Semantic Search ===")

    # Index the files
    print("Indexing files...")
    search_provider.index_files(test_files)
    print("Indexing complete!")

    # Test searches
    test_queries = [
        "function to add numbers",
        "user class with email",
        "HTTP client with timeout",
        "calculate product",
        "API request methods"
    ]

    for query in test_queries:
        print(f"\nSearching for: '{query}'")
        results = search_provider.search(query, max_results=5)

        if results.chunks:
            print(f"Found {len(results.chunks)} results:")
            for i, chunk in enumerate(results.chunks, 1):
                file_name = Path(chunk['path']).name
                lines = chunk['lines']
                print(f"  {i}. {file_name}:{lines[0]}-{lines[1]} (score: {chunk['score']:.3f})")
                # Show a snippet of the content
                content_preview = chunk['content'][:100].replace('\n', ' ')
                print(f"     Preview: {content_preview}...")
        else:
            print("  No results found")


def main():
    """Main test function."""
    print("=== Semantic Search Background Initialization Test ===\n")

    # Create a temporary directory for our test
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        print(f"Created test directory: {test_dir}")

        # Create test files
        test_files = create_test_files(test_dir)
        print(f"Created {len(test_files)} test files\n")

        # Initialize the semantic search
        print("Starting background initialization of semantic search...")
        initializer = SemanticSearchInitializer(test_dir)
        initializer.start()

        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(
            target=monitor_initialization,
            args=(initializer,),
            daemon=True
        )
        monitor_thread.start()

        # Wait for initialization to complete
        print("Waiting for initialization to complete...")
        completed = initializer.wait_for_completion(timeout=120)  # 2 minute timeout

        if completed:
            search_provider = initializer.get_result()
            if search_provider:
                print("\nSemantic search initialized successfully!")

                # Test the search functionality
                test_semantic_search(search_provider, test_files)
            else:
                error = initializer.get_error()
                print(f"\nFailed to get search provider: {error}")
        else:
            error = initializer.get_error()
            print(f"\nInitialization failed or timed out: {error}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()