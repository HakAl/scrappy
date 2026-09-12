"""The CI gate's declared controls must match the controls that actually exist.

scripts/assert_positive_control.py gates the only CI job that verifies containment at
runtime, and it does so by requiring an EXACT set of test identities. That set is
declared in the script, so it is a second list that can drift away from the first one
silently. The launcher's creation destinations had exactly this shape (scrappy-31k9) and
the fix there was the same: hold the two lists in step with a test.

Drift in either direction is a real failure. A control DELETED from the module but left
in the declared set makes the job fail forever on a report that is actually correct. A
control ADDED to the module but not declared means the job keeps passing while the new
control is never required to run, which is the silent direction and the dangerous one.
"""

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "assert_positive_control.py"
CONTROL_MODULE_PATH = REPO_ROOT / "tests" / "containment" / "test_positive_control.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("assert_positive_control", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _declared_test_functions(path: Path) -> set[str]:
    """Every top-level ``test_`` function in the module, read from its SOURCE.

    Parsed rather than imported: importing the positive control module outside the
    launcher is pointless (every test in it would skip) and the question here is purely
    about what the file declares.
    """
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_the_gate_requires_exactly_the_controls_that_exist():
    gate = _load_gate()
    declared_names = {name for _classname, name in gate.REQUIRED_CONTROLS}
    actual_names = _declared_test_functions(CONTROL_MODULE_PATH)

    assert declared_names == actual_names, (
        "scripts/assert_positive_control.py and tests/containment/test_positive_control.py "
        f"have drifted. Declared but absent: {sorted(declared_names - actual_names)}. "
        f"Present but not required by the CI gate: {sorted(actual_names - declared_names)}."
    )


def test_every_required_control_names_the_positive_control_module():
    gate = _load_gate()
    classnames = {classname for classname, _name in gate.REQUIRED_CONTROLS}

    assert classnames == {"tests.containment.test_positive_control"}, classnames
