import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from src.agent_tools.tools.python_tools import AnalyzePythonDependenciesTool
from src.agent_tools.tools.base import ToolContext


# --- Fixtures ---

@pytest.fixture
def mock_context(tmp_path):
    """Creates a tool context backed by a real temporary directory."""
    context = MagicMock(spec=ToolContext)
    context.project_root = tmp_path
    context.is_safe_path = Mock(return_value=True)
    return context


@pytest.fixture
def tool():
    return AnalyzePythonDependenciesTool()


# --- Tests ---

class TestDependencyAnalysisLogic:

    def test_ignore_stdlib(self, tool, mock_context):
        """Should filter out standard library modules."""
        code = """
import os
import sys
import json
from datetime import datetime
import requests
"""
        (mock_context.project_root / "main.py").write_text(code)

        result = tool.execute(mock_context)

        assert result.success
        # os, sys, json, datetime are stdlib
        assert "os" not in result.metadata["packages"]
        assert "json" not in result.metadata["packages"]
        # requests is 3rd party
        assert "requests" in result.metadata["packages"]

    def test_ignore_local_modules(self, tool, mock_context):
        """Should filter out imports that match local file names."""
        # Create a local module
        (mock_context.project_root / "utils.py").write_text("def help(): pass")

        # Import that local module
        code = """
import utils
import requests
"""
        (mock_context.project_root / "main.py").write_text(code)

        result = tool.execute(mock_context)

        assert result.success
        assert "utils" not in result.metadata["packages"]
        assert "requests" in result.metadata["packages"]

    def test_import_syntax_parsing(self, tool, mock_context):
        """Should handle various import styles."""
        code = """
import pandas
import numpy as np
from flask import Flask
from sqlalchemy.orm import sessionmaker
import boto3, botocore
"""
        (mock_context.project_root / "app.py").write_text(code)

        result = tool.execute(mock_context)

        assert result.success
        pkgs = result.metadata["packages"]
        assert "pandas" in pkgs
        assert "numpy" in pkgs
        assert "Flask" in pkgs  # Capitalized due to mapping
        assert "SQLAlchemy" in pkgs  # Mapped from sqlalchemy
        assert "boto3" in pkgs
        assert "botocore" in pkgs

    def test_pypi_name_mapping(self, tool, mock_context):
        """Should map import names to correct PyPI package names."""
        code = """
import cv2
import yaml
import bs4
from PIL import Image
"""
        (mock_context.project_root / "vision.py").write_text(code)

        result = tool.execute(mock_context)

        assert result.success
        requirements = result.metadata["requirements_content"]

        # Check mappings defined in IMPORT_TO_PYPI
        assert "opencv-python" in requirements  # cv2
        assert "PyYAML" in requirements  # yaml
        assert "beautifulsoup4" in requirements  # bs4
        assert "Pillow" in requirements  # PIL

    def test_directory_exclusions(self, tool, mock_context):
        """Should skip specific directories like venv and node_modules."""
        # Create a file in a skipped directory
        venv_dir = mock_context.project_root / "venv"
        venv_dir.mkdir()
        (venv_dir / "lib.py").write_text("import unknown_lib")

        # Create a valid file
        (mock_context.project_root / "src").mkdir()
        (mock_context.project_root / "src/main.py").write_text("import requests")

        result = tool.execute(mock_context)

        assert result.success
        assert "requests" in result.metadata["packages"]
        assert "unknown_lib" not in result.metadata["packages"]

# todo
    # def test_custom_exclusions(self, tool, mock_context):
    #     """Should respect exclude_patterns parameter."""
    #     (mock_context.project_root / "test_main.py").write_text("import pytest")
    #     (mock_context.project_root / "main.py").write_text("import requests")
    #
    #     # Exclude 'test' files
    #     result = tool.execute(mock_context, exclude_patterns="test")
    #
    #     assert result.success
    #     assert "requests" in result.metadata["packages"]
    #     assert "pytest" not in result.metadata["packages"]

    def test_version_detection(self, tool, mock_context):
        """Should attempt to resolve versions using pip show."""
        (mock_context.project_root / "main.py").write_text("import requests")

        # Mock subprocess.run to simulate 'pip show requests'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Name: requests\nVersion: 2.31.0\nSummary: HTTP"

            result = tool.execute(mock_context, include_versions=True)

            assert result.success
            assert "requests==2.31.0" in result.metadata["requirements_content"]
            mock_run.assert_called()

    def test_version_detection_failure(self, tool, mock_context):
        """Should fall back to no version if pip fails."""
        (mock_context.project_root / "main.py").write_text("import requests")

        with patch("subprocess.run") as mock_run:
            # Simulate package not found in environment
            mock_run.return_value.returncode = 1

            result = tool.execute(mock_context, include_versions=True)

            assert result.success
            # Should list package but without version
            content = result.metadata["requirements_content"]
            assert "requests" in content
            assert "requests==" not in content


class TestToolExecution:

    def test_empty_project(self, tool, mock_context):
        """Should handle project with no python files."""
        result = tool.execute(mock_context)

        assert not result.success
        assert "No Python files found" in result.error

    def test_only_stdlib_project(self, tool, mock_context):
        """Should return specific message if only stdlib is used."""
        (mock_context.project_root / "main.py").write_text("import os\nimport sys")

        result = tool.execute(mock_context)

        assert result.success
        assert "No third-party dependencies" in result.output

    def test_unsafe_path(self, tool, mock_context):
        """Should reject unsafe paths."""
        mock_context.is_safe_path.return_value = False

        result = tool.execute(mock_context, directory="../outside")

        assert not result.success
        assert "outside project" in result.error

    def test_broken_syntax_tolerance(self, tool, mock_context):
        """Should skip files with syntax errors but continue processing."""
        # File 1: Syntax error
        (mock_context.project_root / "broken.py").write_text("import... what?")
        # File 2: Valid
        (mock_context.project_root / "valid.py").write_text("import requests")

        result = tool.execute(mock_context)

        assert result.success
        assert "requests" in result.metadata["packages"]