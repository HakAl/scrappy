#!/usr/bin/env python3

# THIS TEST IS FOR BENCHMARK AND UX TESTS DO NOT DELETE

"""
Integration test: Spring Boot + Vite React task via /agent CLI command.

This test runs the actual llm-team agent command (not Python API)
to create a full-stack web application.

IMPORTANT: This test requires:
- API keys configured (GEMINI_API_KEY, CEREBRAS_API_KEY, etc.)
- Network access to LLM providers
- ~2 minutes runtime
- Cleanup of .llm_* cache files for reproducibility

Marked as skipped by default - run manually with:
    pytest tests/test_agent_spring_vite_integration.py -k spring_vite --run-integration
"""
import pytest
import subprocess
import time
import shutil
import sys
import io
from pathlib import Path

# Benchmark test - excluded by default, run with: pytest -m benchmark
pytestmark = pytest.mark.benchmark


def _setup_windows_unicode():
    """Fix Windows Unicode issues - only call when actually running tests."""
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


@pytest.fixture
def clean_test_environment():
    """Clean up cached state files before and after test."""
    project_root = Path(__file__).parent.parent

    # Files to clean
    cache_files = [
        ".llm_team_context.json",
        ".llm_response_cache.json",
        ".llm_rate_limits.json",
        ".llm_agent_audit.json",
        ".spring_vite_audit.json",
    ]

    # Clean before test
    for cache_file in cache_files:
        cache_path = project_root / cache_file
        if cache_path.exists():
            cache_path.unlink()

    # Remove any previous website directory
    website_dir = project_root / "website"
    if website_dir.exists():
        shutil.rmtree(website_dir)

    yield project_root

    # Clean after test (optional - leave for inspection)
    # for cache_file in cache_files:
    #     cache_path = project_root / cache_file
    #     if cache_path.exists():
    #         cache_path.unlink()



def test_agent_spring_vite_full_stack(clean_test_environment):
    """
    Test the agent's ability to create a full-stack Spring + React app.

    This is a comprehensive integration test that:
    1. Invokes the /agent CLI command with --auto-confirm
    2. Verifies backend files are created
    3. Verifies frontend files are created
    4. Checks for proper project structure

    Models Used:
    - Planner: Gemini (gemini-2.5-flash-lite or fallback)
    - Executor: Cerebras
    - Brain: Cerebras (default)
    """
    project_root = clean_test_environment

    # Task definition
    task = """
    Create a new directory called 'website/' with:

    1. A Spring Boot REST API (Java) with:
       - User registration endpoint (POST /api/auth/register)
       - Login endpoint (POST /api/auth/login)
       - Password reset request endpoint (POST /api/auth/password-reset)
       - Use JWT for authentication
       - Include basic User entity and in-memory H2 database

    2. A Vite + React frontend with:
       - Landing page (/)
       - Login page (/login)
       - Register page (/register)
       - Password reset page (/reset-password)
       - Basic routing with React Router
       - Axios for API calls

    Start by creating the directory structure, then implement the backend, then the frontend.
    Keep implementations simple but functional.
    """

    # Run the agent via CLI
    print("\n" + "=" * 70)
    print("RUNNING: llm-team agent command")
    print("=" * 70)

    start_time = time.time()

    result = subprocess.run(
        [
            "python", "llm_team.py", "agent",
            task,
            "--auto-confirm",
            "--max-iterations", "50",
            "--no-checkpoint",  # Skip git checkpoint for test
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout
        encoding='utf-8',
        errors='replace',  # Handle unicode issues on Windows
    )

    elapsed = time.time() - start_time

    print(f"\nAgent completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
    print(f"Exit code: {result.returncode}")

    # Print stdout
    print("\n" + "=" * 70)
    print("AGENT OUTPUT:")
    print("=" * 70)
    print(result.stdout)

    if result.stderr:
        print("\n" + "=" * 70)
        print("STDERR:")
        print("=" * 70)
        print(result.stderr)

    # Verify results
    website_dir = project_root / "website"

    # Check backend structure
    backend_dir = website_dir / "backend"
    assert backend_dir.exists(), "Backend directory not created"

    # Check for key backend files (flexible - agent may use different package names)
    expected_backend_patterns = [
        "pom.xml",
        "**/Application.java",  # Main class (any package)
        "**/User.java",         # User entity
        "**/AuthController.java",  # Auth endpoints
        "src/main/resources/application.properties",
    ]

    backend_files_found = []
    for pattern in expected_backend_patterns:
        if "*" in pattern:
            # Glob pattern
            matches = list(backend_dir.glob(pattern))
            if matches:
                backend_files_found.append(str(matches[0].relative_to(backend_dir)))
        else:
            # Exact path
            file_path = backend_dir / pattern
            if file_path.exists():
                backend_files_found.append(pattern)

    print(f"\nBackend files found: {len(backend_files_found)}/{len(expected_backend_patterns)}")
    for f in backend_files_found:
        print(f"  ✓ {f}")

    # Check frontend structure
    frontend_dir = website_dir / "frontend"
    assert frontend_dir.exists(), "Frontend directory not created"

    # Check for key frontend files
    expected_frontend_files = [
        "package.json",
        "src/pages/LoginPage.jsx",
        "src/pages/RegisterPage.jsx",
        "src/services/apiService.js",
    ]

    frontend_files_found = []
    for expected in expected_frontend_files:
        file_path = frontend_dir / expected
        if file_path.exists():
            frontend_files_found.append(expected)

    print(f"\nFrontend files found: {len(frontend_files_found)}/{len(expected_frontend_files)}")
    for f in frontend_files_found:
        print(f"  ✓ {f}")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY:")
    print("=" * 70)
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Backend completeness: {len(backend_files_found)}/{len(expected_backend_patterns)}")
    print(f"Frontend completeness: {len(frontend_files_found)}/{len(expected_frontend_files)}")

    # Assert minimum requirements
    assert len(backend_files_found) >= 3, f"Too few backend files: {backend_files_found}"
    assert len(frontend_files_found) >= 2, f"Too few frontend files: {frontend_files_found}"

    # Check for known issues
    if (frontend_dir / "temp-vite-app").exists():
        print("\n⚠️  WARNING: temp-vite-app directory not cleaned up (dangerous command blocked)")

    # Check if App.jsx exists (known issue - often missing)
    app_jsx = frontend_dir / "src" / "App.jsx"
    if not app_jsx.exists():
        print("⚠️  WARNING: App.jsx not created (routing not set up)")

    main_jsx = frontend_dir / "src" / "main.jsx"
    if not main_jsx.exists():
        print("⚠️  WARNING: main.jsx not created (React entry point missing)")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    # Allow running directly for manual testing
    import sys

    # Remove the skip marker for direct execution
    test_agent_spring_vite_full_stack.__pytest_mark__ = None

    # Create a simple fixture substitute
    project_root = Path(__file__).parent.parent

    # Clean cache files
    cache_files = [
        ".llm_team_context.json",
        ".llm_response_cache.json",
        ".llm_rate_limits.json",
        ".llm_agent_audit.json",
        ".spring_vite_audit.json",
    ]

    for cache_file in cache_files:
        cache_path = project_root / cache_file
        if cache_path.exists():
            print(f"Removing {cache_file}")
            cache_path.unlink()

    # Remove website directory
    website_dir = project_root / "website"
    if website_dir.exists():
        print("Removing website/")
        shutil.rmtree(website_dir)

    # Run the test
    test_agent_spring_vite_full_stack(project_root)
