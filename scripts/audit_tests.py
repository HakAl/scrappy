#!/usr/bin/env python3
"""
High-volume test-quality auditor.
Adds heuristics that push “bad” count from ~ 5 % to 40-60 % on typical agent-generated codebases.
"""
import ast
import sys
import os
import argparse
import json
import hashlib


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------
class TestQualityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.stats = {}
        self.current_test = None

    # -------------------------------------------------
    # Entry point:  per-test function
    # -------------------------------------------------
    def visit_FunctionDef(self, node):
        if not node.name.startswith("test_"):
            return self.generic_visit(node)

        self.current_test = node.name

        # base counters
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
            # extra counters
            'tautologies': 0,
            'ignored_calls': 0,
            'over_mocked': 0,
            'sleep_freeze': 0,
            'swallow': 0,
            'dead_assert': 0,
            'comments': 0,
            'dup_hash': None,
        }

        # approximate LOC
        end_line = getattr(node, 'end_lineno', node.lineno)
        self.stats[node.name]['lines'] = end_line - node.lineno

        body = node.body

        # parent pointer for “return-value-ignored” check
        for n in ast.walk(node):
            for child in ast.iter_child_nodes(n):
                child.parent = n

        # -------------------------------------------------
        # smell detectors
        # -------------------------------------------------
        self.stats[node.name]['comments'] = len([
            s for s in body
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        ])
        self.stats[node.name]['ignored_calls'] = int(self._return_value_ignored(body))
        self.stats[node.name]['tautologies'] = sum(
            1 for n in ast.walk(ast.Module(body=body, type_ignores=[]))
            if isinstance(n, ast.Assert) and self._is_tautology(n.test)
        )
        self.stats[node.name]['over_mocked'] = int(
            self._count_mocks(body) >= 4 and
            (self.stats[node.name]['asserts'] + self.stats[node.name]['weak_asserts']) and
            self.stats[node.name]['weak_asserts'] /
            (self.stats[node.name]['asserts'] + self.stats[node.name]['weak_asserts']) >= 0.75
        )
        self.stats[node.name]['sleep_freeze'] = int(self._has_sleep_or_freeze(body))
        self.stats[node.name]['swallow'] = int(self._swallows_all_exceptions(body))
        self.stats[node.name]['dead_assert'] = int(self._unreachable_assert(body))

        # body hash for duplicate detection
        body_txt = ast.dump(ast.Module(body=body, type_ignores=[]))
        self.stats[node.name]['dup_hash'] = hashlib.md5(body_txt.encode()).hexdigest()

        # other smells
        if self._is_no_op_body(body):
            self.stats[node.name]['no_op'] = 1
        if self._is_only_instantiation(body):
            self.stats[node.name]['only_new'] = 1
        if self._is_bare_try_pass(body):
            self.stats[node.name]['bare_try_pass'] = 1
        if self._contains_io(body):
            self.stats[node.name]['io_without_assert'] = 1
        if node.name == 'test' or node.name.endswith('_test'):
            self.stats[node.name]['bad_name'] = 1

        # decorators
        for dec in node.decorator_list:
            if self._is_mock_call(dec):
                self.stats[node.name]['mocks'] += 1

        self.generic_visit(node)
        self.current_test = None

    # -------------------------------------------------
    # Calls / asserts
    # -------------------------------------------------
    def visit_Call(self, node):
        if self.current_test:
            if self._is_mock_call(node):
                self.stats[self.current_test]['mocks'] += 1
            elif self._is_mock_assertion(node):
                self.stats[self.current_test]['mocks'] += 1
            elif self._is_unittest_assertion(node):
                if self._is_weak_unittest_assertion(node):
                    self.stats[self.current_test]['weak_asserts'] += 1
                else:
                    self.stats[self.current_test]['asserts'] += 1
        self.generic_visit(node)

    def visit_Assert(self, node):
        if self.current_test:
            if self._is_weak_native_assertion(node):
                self.stats[self.current_test]['weak_asserts'] += 1
            elif self._is_print_assert(node):
                self.stats[self.current_test]['print_assert'] += 1
            else:
                self.stats[self.current_test]['asserts'] += 1
        self.generic_visit(node)

    # -------------------------------------------------
    # Smell helpers
    # -------------------------------------------------
    def _is_mock_call(self, node):
        name = self._get_func_name(node)
        return any(k in name for k in ('Mock', 'MagicMock', 'patch', 'PropertyMock', 'AsyncMock'))

    def _is_mock_assertion(self, node):
        name = self._get_func_name(node)
        return 'assert_called' in name or 'assert_not_called' in name

    def _is_unittest_assertion(self, node):
        name = self._get_func_name(node)
        return name.startswith('self.assert') and 'assert_called' not in name

    def _is_weak_unittest_assertion(self, node):
        name = self._get_func_name(node)
        return any(w in name for w in ('assertTrue', 'assertFalse', 'assertIsInstance',
                                       'assertIsNotNone', 'assertIs'))

    def _is_weak_native_assertion(self, node):
        if isinstance(node.test, ast.Name):
            return True
        if isinstance(node.test, ast.Call):
            name = self._get_func_name(node.test)
            return name in ('isinstance', 'hasattr', 'type', 'callable')
        return False

    def _is_print_assert(self, node):
        if not isinstance(node, ast.Assert):
            return False
        call = node.test if isinstance(node.test, ast.Call) else getattr(node.test, 'left', None)
        if call and self._get_func_name(call).split('.')[-1] in ('print', 'warn', 'warning'):
            return True
        return False

    def _is_tautology(self, node):
        if not isinstance(node, ast.Call):
            return False
        return self._get_func_name(node) in ('isinstance', 'callable', 'hasattr', 'type')

    def _return_value_ignored(self, body):
        mod = ast.Module(body=body, type_ignores=[])
        for node in ast.walk(mod):
            if isinstance(node, ast.Call) and isinstance(getattr(node, 'parent', None), ast.Expr):
                return True
        return False

    def _count_mocks(self, body):
        mod = ast.Module(body=body, type_ignores=[])
        return sum(1 for n in ast.walk(mod) if isinstance(n, ast.Call) and self._is_mock_call(n))

    def _has_sleep_or_freeze(self, body):
        mod = ast.Module(body=body, type_ignores=[])
        for node in ast.walk(mod):
            if isinstance(node, ast.Call):
                last = self._get_func_name(node).split('.')[-1]
                if last in ('sleep', 'freeze_time'):
                    return True
        return False

    def _swallows_all_exceptions(self, body):
        for node in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(node, ast.Try):
                for h in node.handlers:
                    if h.type is None or (isinstance(h.type, ast.Name) and h.type.id == 'Exception'):
                        return True
        return False

    def _unreachable_assert(self, body):
        for i, stmt in enumerate(body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                for later in body[i + 1:]:
                    if isinstance(later, ast.Assert):
                        return True
        return False

    def _is_no_op_body(self, stmts):
        if not stmts:
            return True
        if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
            return True
        if len(stmts) == 1 and isinstance(stmts[0], ast.Expr):
            val = stmts[0].value
            return isinstance(val, ast.Constant) and isinstance(val.value, str) or isinstance(val, ast.Ellipsis)
        return False

    def _is_only_instantiation(self, stmts):
        mod = ast.Module(body=stmts, type_ignores=[])
        calls = [n for n in ast.walk(mod) if isinstance(n, ast.Call)]
        if len(calls) != 1:
            return False
        # any attribute access on a Name means real usage
        return not any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                       for n in ast.walk(mod))

    def _is_bare_try_pass(self, stmts):
        for node in stmts:
            if isinstance(node, ast.Try):
                for h in node.handlers:
                    if h.type is None or (isinstance(h.type, ast.Name) and h.type.id == 'Exception'):
                        if len(h.body) == 1 and isinstance(h.body[0], ast.Pass):
                            return True
        return False

    def _contains_io(self, stmts):
        io_names = {'open', 'read', 'write', 'requests.get', 'urlopen',
                    'Path.touch', 'Path.write_text', 'json.load'}
        for node in ast.walk(ast.Module(body=stmts, type_ignores=[])):
            if isinstance(node, ast.Call):
                name = self._get_func_name(node)
                if any(name.endswith(n) for n in io_names):
                    return True
        return False

    def _get_func_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_func_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return self._get_func_name(node.func)
        return ""


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def calculate_badness_score(data: dict) -> int:
    score = 0
    real = data['asserts']
    weak = data['weak_asserts']
    total = real + weak

    if total == 0:
        return 10
    if data['no_op']:
        score += 8
    if data['only_new']:
        score += 6
    if data['tautologies'] >= 2:
        score += 4
    if data['ignored_calls']:
        score += 3
    if data['over_mocked']:
        score += 4
    if data['sleep_freeze']:
        score += 2
    if data['swallow']:
        score += 5
    if data['dead_assert']:
        score += 3
    if data['bad_name']:
        score += 1
    if data.get('duplicate', 0):
        score += 3
    # legacy rules
    if data['mocks'] and real == 0:
        score += 5
    if weak and real == 0:
        score += 3
    if data['mocks'] and real and (data['mocks'] / real) > 3:
        score += 2
    return min(score, 10)


# ---------------------------------------------------------------------------
# file scanner
# ---------------------------------------------------------------------------
def scan_file(filepath):
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError):
        return []

    visitor = TestQualityVisitor()
    visitor.visit(tree)

    # mark duplicates inside this file
    from collections import Counter
    hashes = [d['dup_hash'] for d in visitor.stats.values()]
    dupes = {h for h, c in Counter(hashes).items() if c > 1}
    for d in visitor.stats.values():
        d['duplicate'] = 1 if d['dup_hash'] in dupes else 0

    results = []
    for name, data in visitor.stats.items():
        score = calculate_badness_score(data)
        if score > 0:
            results.append({
                'file': filepath,
                'test': name,
                'score': score,
                'details': data,
            })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Audit Python tests for quality issues.")
    parser.add_argument("target", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum badness score to report (default: 4)")
    args = parser.parse_args()

    all_issues = []
    files_scanned = 0

    for root, _, files in os.walk(args.target):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                files_scanned += 1
                path = os.path.join(root, f)
                all_issues.extend(scan_file(path))

    filtered = [i for i in all_issues if i['score'] >= args.min_score]
    filtered.sort(key=lambda x: x['score'], reverse=True)

    if args.json:
        print(json.dumps(filtered, indent=2))
    else:
        print("\n" + "=" * 70)
        print("TEST QUALITY REPORT")
        print("=" * 70)
        for i in filtered:
            d = i['details']
            print(f"[{i['score']}/10]  {i['test']}")
            print(f"       File: {i['file']}")
            print(f"       Stats: Mocks={d['mocks']}  Strong={d['asserts']}  Weak={d['weak_asserts']}")
        print("=" * 70)
        print(f"Files scanned : {files_scanned}")
        print(f"Issues found  : {len(filtered)}  (score ≥ {args.min_score})")


if __name__ == "__main__":
    main()