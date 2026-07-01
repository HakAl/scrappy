"""
tests/cli/test_codebase.py
~~~~~~~~~~~~~~~~~~~~~~~~~~

Comprehensive, offline test-suite for src/cli/codebase.py::CLICodebaseAnalysis.

Run with:
    pytest tests/cli/test_codebase.py -q
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.helpers import MockIO

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------



class FakeOrchestrator:
    """Orchestrator double that returns canned responses."""
    def __init__(self, llm_reply: str = "fake-summary"):
        self.brain = Mock()
        self.context = Mock()
        self.working_memory = Mock()
        self._llm_reply = llm_reply

    def delegate(self, brain, prompt, **kwargs):
        resp = Mock()
        resp.content = self._llm_reply
        return resp


@pytest.fixture
def tmp_project() -> Path:
    """Create a miniature fake project on disk."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "README.md").write_text("# Demo\nA tiny project.")
        (root / "requirements.txt").write_text("requests\n")
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("print('hello')")
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text("def test_ok(): pass")
        yield root


@pytest.fixture
def analysis():
    """Fresh CLICodebaseAnalysis instance with fake orchestrator."""
    orch = FakeOrchestrator()
    io = MockIO()
    from scrappy.cli.codebase import CLICodebaseAnalysis
    return CLICodebaseAnalysis(orch, io)




# ---------------------------------------------------------------------------
# Private helper tests
# ---------------------------------------------------------------------------

def test_find_source_files(analysis, tmp_project: Path):
    files = analysis._find_source_files(tmp_project)
    assert "python" in files
    python_files = {Path(f).name for f in files["python"]}
    assert "main.py" in python_files
    assert "test_main.py" in python_files


def test_analyze_structure(analysis, tmp_project: Path):
    files = analysis._find_source_files(tmp_project)
    struct = analysis._analyze_structure(tmp_project, files)
    assert struct["total_files"] == 4
    assert struct["has_readme"] is True
    assert struct["has_requirements"] is True
    assert "src" in struct["directories"]


def test_read_key_files(analysis, tmp_project: Path):
    files = analysis._find_source_files(tmp_project)
    contents = analysis._read_key_files(tmp_project, files)
    assert "README.md" in contents
    assert "requirements.txt" in contents
    assert "# Demo" in contents["README.md"]


def test_generate_codebase_summary(analysis, tmp_project: Path):
    files = analysis._find_source_files(tmp_project)
    struct = analysis._analyze_structure(tmp_project, files)
    contents = analysis._read_key_files(tmp_project, files)
    summary = analysis._generate_codebase_summary(tmp_project, struct, contents)
    assert summary == "fake-summary"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_read_key_files_truncation(analysis):
    """Ensure truncation constants are respected."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        big = root / "big.py"
        big.write_text("x" * 50_000)
        files = {"python": ["big.py"]}
        contents = analysis._read_key_files(root, files)
        assert len(contents["big.py"]) < 50_000
        assert contents["big.py"].endswith("... (truncated)")


def test_skip_hidden_and_special_dirs(analysis):
    """Hidden directories and SKIP_DIRS should be ignored."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".git").mkdir()
        (root / "__pycache__").mkdir()
        (root / "src").mkdir()
        (root / "src" / "ok.py").write_text("pass")
        files = analysis._find_source_files(root)
        assert not any(".git" in f for f in files["python"])
        assert not any("__pycache__" in f for f in files["python"])

