import ast
import sys
import os
import argparse
import json


class TestQualityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.stats = {}
        self.current_test = None

    def visit_FunctionDef(self, node):
        if node.name.startswith("test_"):
            self.current_test = node.name
            self.stats[node.name] = {
                'mocks': 0,
                'asserts': 0,
                'weak_asserts': 0,
                'lines': 0,
                'no_op': 0,
                'only_new': 0,
                'print_assert': 0,
                'bare_try_pass': 0,
                'io_without_assert': 0,
                'bad_name': 0,
                'comment_lines': 0,
            }
            end_line = getattr(node, 'end_lineno', node.lineno)
            self.stats[node.name]['lines'] = end_line - node.lineno

            # count comment-only lines inside the function
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                        and isinstance(stmt.value.value, str) and stmt.value.value.strip():
                    self.stats[node.name]['comment_lines'] += stmt.value.value.count('\n') + 1

            # ---  NEW SMELLS  ---
            if self._is_no_op_body(node.body):
                self.stats[node.name]['no_op'] = 1
            if self._is_only_instantiation(node.body):
                self.stats[node.name]['only_new'] = 1
            if self._is_bare_try_pass(node.body):
                self.stats[node.name]['bare_try_pass'] = 1
            if self._contains_io(node.body):
                # crude: if no real assert exists we flag it
                self.stats[node.name]['io_without_assert'] = 1
            if node.name == 'test' or node.name.endswith('_test'):
                self.stats[node.name]['bad_name'] = 1

            # walk decorators / calls as before
            for decorator in node.decorator_list:
                if self._is_mock_call(decorator):
                    self.stats[node.name]['mocks'] += 1
            self.generic_visit(node)
            self.current_test = None

    def visit_Call(self, node):
        if self.current_test:
            # 1. Mock Definitions
            if self._is_mock_call(node):
                self.stats[self.current_test]['mocks'] += 1

            # 2. Mock Assertions (mock.assert_called...)
            elif self._is_mock_assertion(node):
                self.stats[self.current_test]['mocks'] += 1

            # 3. Real Assertions (self.assert...)
            elif self._is_unittest_assertion(node):
                if self._is_weak_unittest_assertion(node):
                    self.stats[self.current_test]['weak_asserts'] += 1
                else:
                    self.stats[self.current_test]['asserts'] += 1

        self.generic_visit(node)

    def visit_Assert(self, node):
        if not self.current_test:
            return self.generic_visit(node)
        if self._is_weak_native_assertion(node):
            self.stats[self.current_test]['weak_asserts'] += 1
        elif self._is_print_assert(node):
            self.stats[self.current_test]['print_assert'] += 1
        else:
            self.stats[self.current_test]['asserts'] += 1
        self.generic_visit(node)

    # -------------  NEW HELPERS  -------------

    def _is_no_op_body(self, stmts):
        """True if the body is only `pass`, `...`, or a doc-string."""
        if not stmts:
            return True
        if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
            return True
        if len(stmts) == 1 and isinstance(stmts[0], ast.Expr) and \
                isinstance(stmts[0].value, ast.Constant) and \
                isinstance(stmts[0].value.value, str):
            return True  # lone doc-string
        if len(stmts) == 1 and isinstance(stmts[0], ast.Expr) and \
                isinstance(stmts[0].value, ast.Ellipsis):
            return True
        return False

    def _is_only_instantiation(self, stmts):
        """Body does nothing except `MyClass()` or `MyClass(x=1)`."""
        calls = [n for n in ast.walk(ast.Module(body=stmts, type_ignores=[]))
                 if isinstance(n, ast.Call)]
        if len(calls) != 1:
            return False
        # Ensure no attribute access / method call on the instance
        for node in ast.walk(ast.Module(body=stmts, type_ignores=[])):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                return False  # instance.attr or instance.method()
        return True

    def _is_print_assert(self, node):
        """Assert on print()/log()/warnings.warn() return value."""
        if not isinstance(node, ast.Assert):
            return False
        call = None
        if isinstance(node.test, ast.Call):
            call = node.test
        elif isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Call):
            call = node.test.left
        if call and self._get_func_name(call).split('.')[-1] in {'print', 'warn', 'warning'}:
            return True
        return False

    def _is_bare_try_pass(self, stmts):
        """try: something  except: pass  (swallows all errors)."""
        for stmt in stmts:
            if isinstance(stmt, ast.Try):
                for handler in stmt.handlers:
                    if handler.type is None or (
                            isinstance(handler.type, ast.Name) and
                            handler.type.id == 'Exception'
                    ):
                        if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                            return True
        return False

    def _contains_io(self, stmts):
        """Look for obvious I/O calls that are never asserted on."""
        io_names = {'open', 'read', 'write', 'requests.get', 'urlopen',
                    'Path.touch', 'Path.write_text', 'json.load'}
        for node in ast.walk(ast.Module(body=stmts, type_ignores=[])):
            if isinstance(node, ast.Call):
                name = self._get_func_name(node)
                if any(name.endswith(n) for n in io_names):
                    return True
        return False

    # --- Detection Helpers ---

    def _is_mock_call(self, node):
        name = self._get_func_name(node)
        mock_keywords = ['Mock', 'MagicMock', 'patch', 'PropertyMock', 'AsyncMock']
        return any(k in name for k in mock_keywords)

    def _is_mock_assertion(self, node):
        name = self._get_func_name(node)
        return 'assert_called' in name or 'assert_not_called' in name

    def _is_unittest_assertion(self, node):
        name = self._get_func_name(node)
        # Must start with self.assert, but NOT be a mock assert
        return name.startswith('self.assert') and 'assert_called' not in name

    def _is_weak_unittest_assertion(self, node):
        """Detects self.assertTrue, self.assertIsInstance, self.assertIsNotNone"""
        name = self._get_func_name(node)
        weak_list = ['assertTrue', 'assertFalse', 'assertIsInstance', 'assertIsNotNone', 'assertIs']
        return any(w in name for w in weak_list)

    def _is_weak_native_assertion(self, node):
        """Detects 'assert obj', 'assert isinstance(...)'"""
        # Case 1: assert obj (checking truthiness only)
        if isinstance(node.test, ast.Name):
            return True

        # Case 2: assert isinstance(...) or assert hasattr(...)
        if isinstance(node.test, ast.Call):
            name = self._get_func_name(node.test)
            if name in ['isinstance', 'hasattr', 'type', 'callable']:
                return True

        return False

    def _get_func_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_func_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_func_name(node.func)
        return ""


def calculate_badness_score(mocks, asserts, weak_asserts, lines, details):
    score = 0
    total_asserts = asserts + weak_asserts

    if total_asserts == 0:
        score += 10
        return score

    if details.get('no_op'):
        score += 8
    if details.get('only_new'):
        score += 6
    if details.get('print_assert'):
        score += 4
    if details.get('bare_try_pass'):
        score += 5
    if details.get('io_without_assert') and total_asserts == 0:
        score += 4
    if details.get('bad_name'):
        score += 2

    # keep your original rules
    if mocks > 0 and asserts == 0:
        score += 5
    if weak_asserts and asserts == 0:
        score += 3
    if mocks and asserts and (mocks / asserts) > 3:
        score += 2

    return min(score, 10)


def scan_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read(), filename=filepath)
    except (SyntaxError, UnicodeDecodeError):
        return []

    visitor = TestQualityVisitor()
    visitor.visit(tree)

    results = []
    for test_name, data in visitor.stats.items():
        score = calculate_badness_score(
            data['mocks'], data['asserts'], data['weak_asserts'], data['lines'], data
        )

        # Only return interesting results (Score > 0)
        if score > 0:
            results.append({
                'file': filepath,
                'test': test_name,
                'score': score,
                'details': data
            })
    return results


def main():
    parser = argparse.ArgumentParser(description="Audit Python tests for quality issues.")
    parser.add_argument("target", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum badness score to report (default: 4)")
    args = parser.parse_args()

    all_issues = []
    total_files_scanned = 0
    total_tests_scanned = 0

    # Walk directory
    for root, dirs, files in os.walk(args.target):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                total_files_scanned += 1
                path = os.path.join(root, file)
                file_issues = scan_file(path)

                # We don't have total test count in file_issues,
                # but for stats purposes we only count flagged ones here.
                # In a real tool, we'd track total visitors.
                all_issues.extend(file_issues)

    # Filter by score
    filtered_issues = [i for i in all_issues if i['score'] >= args.min_score]
    filtered_issues.sort(key=lambda x: x['score'], reverse=True)

    if args.json:
        print(json.dumps(filtered_issues, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"TEST QUALITY REPORT")
        print(f"{'=' * 60}")

        for issue in filtered_issues:
            d = issue['details']
            print(f"[{issue['score']}/10] {issue['test']}")
            print(f"       File: {issue['file']}")
            print(f"       Stats: Mocks={d['mocks']}, StrongAsserts={d['asserts']}, WeakAsserts={d['weak_asserts']}")

            reasons = []
            if d['asserts'] + d['weak_asserts'] == 0:
                reasons.append("No assertions")
            elif d['mocks'] > 0 and d['asserts'] == 0:
                reasons.append("Mocks without strong assertions")
            elif d['weak_asserts'] > 0 and d['asserts'] == 0:
                reasons.append("Only weak assertions")

            if reasons:
                print(f"       Flag: {', '.join(reasons)}")
            print("-" * 60)

        print(f"\nSummary:")
        print(f"Files Scanned: {total_files_scanned}")
        print(f"Issues Found:  {len(filtered_issues)} (Score >= {args.min_score})")


if __name__ == "__main__":
    main()