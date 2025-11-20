import ast
import sys
import os


class MockHeavyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.stats = {}  # {test_name: {'mocks': 0, 'asserts': 0, 'lines': 0}}
        self.current_test = None

    def visit_FunctionDef(self, node):
        # Only analyze functions starting with 'test_'
        if node.name.startswith("test_"):
            self.current_test = node.name
            self.stats[node.name] = {'mocks': 0, 'asserts': 0, 'lines': 0}

            # Count lines of code (approximate)
            end_line = getattr(node, 'end_lineno', node.lineno)
            self.stats[node.name]['lines'] = end_line - node.lineno

            # Check decorators for @patch or @mock
            for decorator in node.decorator_list:
                if self._is_mock_call(decorator):
                    self.stats[node.name]['mocks'] += 1

            self.generic_visit(node)
            self.current_test = None

    def visit_Call(self, node):
        if self.current_test:
            # 1. Check for Mock definitions or patches
            if self._is_mock_call(node):
                self.stats[self.current_test]['mocks'] += 1

            # 2. Check for Mock Assertions (e.g., .assert_called_once)
            elif self._is_mock_assertion(node):
                self.stats[self.current_test]['mocks'] += 1

            # 3. Check for Real Assertions (self.assertEqual, etc.)
            elif self._is_real_assertion(node):
                self.stats[self.current_test]['asserts'] += 1

        self.generic_visit(node)

    def visit_Assert(self, node):
        # Handles the 'assert' keyword
        if self.current_test:
            self.stats[self.current_test]['asserts'] += 1
        self.generic_visit(node)

    def _is_mock_call(self, node):
        """Detects Mock(), MagicMock(), patch(), etc."""
        name = self._get_func_name(node)
        mock_keywords = ['Mock', 'MagicMock', 'patch', 'PropertyMock', 'AsyncMock']
        return any(k in name for k in mock_keywords)

    def _is_mock_assertion(self, node):
        """Detects mock.assert_called..."""
        name = self._get_func_name(node)
        return 'assert_called' in name or 'assert_not_called' in name

    def _is_real_assertion(self, node):
        """Detects self.assertEqual, self.assertTrue, etc."""
        name = self._get_func_name(node)
        # Exclude assert_called which is mock-specific
        return name.startswith('self.assert') and 'assert_called' not in name

    def _get_func_name(self, node):
        """Helper to get the name of a called function from AST"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_func_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_func_name(node.func)
        return ""


def scan_file(filepath):
    # Fix: Explicitly enforce utf-8 encoding
    # 'errors="replace"' prevents crashes even if the file has weird binary junk
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source_code = f.read()
            tree = ast.parse(source_code, filename=filepath)
    except (SyntaxError, UnicodeDecodeError) as e:
        # Skip files that aren't valid Python or can't be read
        # print(f"Skipping {filepath} due to error: {e}")
        return

    visitor = MockHeavyVisitor()
    visitor.visit(tree)

    for test, data in visitor.stats.items():
        mocks = data['mocks']
        asserts = data['asserts']
        lines = data['lines']

        # Avoid division by zero
        mock_density = mocks / lines if lines > 0 else 0

        # Logic:
        # 1. "Behavior-less": Mocks exist, but ZERO real assertions.
        # 2. "Over-mocked": More than 40% of the code is just mock setup/checks.
        only_mocks = (mocks > 0 and asserts == 0)

        if only_mocks or mock_density > 0.4:
            print(f"⚠️  Possible Bad Test: {test} ({filepath})")
            print(f"   - Mocks/Patches: {mocks}")
            print(f"   - Real Asserts:  {asserts}")
            print(f"   - Lines of Code: {lines}")
            print(f"   - Reason: {'Only checks mocks' if only_mocks else 'High mock density'}")
            print("-" * 40)


if __name__ == "__main__":
    # Usage: python find_mock_heavy_tests.py tests/
    target_dir = sys.argv[1]
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                scan_file(os.path.join(root, file))