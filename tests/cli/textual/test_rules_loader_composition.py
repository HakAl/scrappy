"""PR-7 F1: the rules loader is COMPOSED at runtime and its rules are CONSUMED.

The proof standard here is deliberate. Asserting that a constructor was called
would pass against a bridge that ignored the loader entirely, and that exact
substitution is why this finding was reopened. So these tests drive the REAL
LangGraphBridge.run_agent and read what actually landed in the run context and
the reminder manager.

Each test uses a NON-DEFAULT loader whose agent_files the production default
does NOT contain. Reverting the bridge to a bare AgentRulesLoader therefore
finds nothing and the consumption assertions fail, which is what makes them
meaningful rather than decorative.

Roots are kept distinct: the rules live under a code root that is never the
process CWD, so "read the injected loader's result" and "scanned wherever the
process happened to stand" cannot be confused.
"""

import json
from unittest.mock import Mock

import pytest

from scrappy.context.agent_rules_loader import (
    AgentRulesLoader,
    create_default_agent_rules_loader,
)
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment


CUSTOM_RULES_FILE = "TEAM_RULES.md"
RULES_MARKER = "rule-marker-from-injected-loader"


class StreamingModelBoundary:
    """The only stubbed seam: the model boundary. Everything else is real."""

    def __init__(self, tool_calls_per_turn=()):
        self._turns = list(tool_calls_per_turn)
        self._turn = 0

    def stream_completion_with_fallback(self, messages=None, selection_type=None, **kwargs):
        tool_calls = self._turns[self._turn] if self._turn < len(self._turns) else []
        self._turn += 1
        fragments = [
            ToolCallFragment(
                id=f"call_{i}", type="function", name=name,
                arguments=json.dumps(args), index=i, complete=True,
            )
            for i, (name, args) in enumerate(tool_calls)
        ]
        if not fragments:
            yield StreamChunk(content="done", model="stub", provider="stub", finish_reason="stop")
            return
        yield StreamChunk(
            content="", tool_call_fragments=fragments,
            model="stub", provider="stub", finish_reason="stop",
        )


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Distinct code root and process CWD, asserted distinct."""
    code_root = tmp_path / "code_root"
    process_cwd = tmp_path / "process_cwd"
    storage_root = tmp_path / "storage_root"
    for d in (code_root, process_cwd, storage_root):
        d.mkdir()
    assert len({str(d.resolve()) for d in (code_root, process_cwd, storage_root)}) == 3
    monkeypatch.chdir(process_cwd)
    return type("Roots", (), {
        "code_root": code_root, "process_cwd": process_cwd, "storage_root": storage_root,
    })()


def build_bridge(rules_loader=None):
    """A REAL LangGraphBridge; only UI transport and the model are doubles."""
    from scrappy.cli.textual.langgraph_bridge import LangGraphBridge
    from scrappy.graph.tools import ToolAdapter

    async_bridge = Mock()
    async_bridge.blocking_confirm_yna.return_value = "a"

    kwargs = dict(
        app=Mock(),
        bridge=async_bridge,
        output_adapter=Mock(),
        orchestrator=StreamingModelBoundary(),
        tool_adapter=ToolAdapter.create_default(profile="full"),
    )
    if rules_loader is not None:
        kwargs["rules_loader"] = rules_loader
    return LangGraphBridge(**kwargs)


def capture_run_context(monkeypatch):
    """Retain the REAL AgentRunContext that run_agent drops in its finally block.

    run_agent sets self._run_context = None on completion, so it cannot be read
    afterwards. Nothing is stubbed here: the production code still builds and
    populates the genuine object, this only keeps a reference to it.
    """
    from scrappy.cli.textual import langgraph_bridge as lgb

    captured = {}
    real_cls = lgb.AgentRunContext

    class Recording(real_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["context"] = self

    monkeypatch.setattr(lgb, "AgentRunContext", Recording)
    return captured


def non_default_loader() -> AgentRulesLoader:
    """A loader the production default is NOT equivalent to.

    It searches a filename absent from AGENT_FILES, so a bare default loader
    cannot find the rules file these tests write.
    """
    return AgentRulesLoader(agent_files=[CUSTOM_RULES_FILE], max_depth=2)


def test_injected_loader_rules_are_consumed_into_run_context_and_reminders(roots, monkeypatch):
    """THE F1 PROOF: a configured loader's rules reach run context and reminders.

    Not a constructor assertion. The bridge really runs, and the assertions read
    what the production code placed in the run context and the reminder manager.
    """
    (roots.code_root / CUSTOM_RULES_FILE).write_text(f"# {RULES_MARKER}\n")
    captured = capture_run_context(monkeypatch)

    bridge = build_bridge(rules_loader=non_default_loader())
    result = bridge.run_agent(task="noop", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"

    context = captured["context"]
    assert context.project_rules, "no project rules were consumed at all"
    assert RULES_MARKER in context.project_rules, (
        "the injected loader's rules did not reach the run context"
    )
    assert context.reminder_manager is not None, (
        "rules were loaded but no reminder manager was created"
    )


def test_bare_default_loader_does_not_find_the_custom_rules(roots):
    """The companion that makes the proof above non-vacuous.

    Same file, same roots, but the production DEFAULT loader. It must find
    nothing, which is exactly why the previous test failing would be a real
    regression signal rather than an environment artefact.
    """
    (roots.code_root / CUSTOM_RULES_FILE).write_text(f"# {RULES_MARKER}\n")

    loaded = create_default_agent_rules_loader().load(roots.code_root)

    # The default does find something: its ancestor walk reaches the repository's
    # own AGENTS.md, because the contained tmp roots live under the repo. What
    # matters is that it never selects OUR custom file, so the marker assertion
    # in the proof above genuinely discriminates.
    selected = None if loaded is None else loaded.source_file.name
    assert selected != CUSTOM_RULES_FILE, (
        "the production default selected the custom file, so the injected-loader "
        "proof would pass even without injection"
    )
    assert loaded is None or RULES_MARKER not in loaded.content, (
        "the default loader surfaced the marker, which would mask a dropped injection"
    )


def test_absent_injection_composes_the_production_default(roots, monkeypatch):
    """No injection must behave exactly as before: AGENTS.md is still found."""
    (roots.code_root / "AGENTS.md").write_text(f"# {RULES_MARKER}\n")
    captured = capture_run_context(monkeypatch)

    bridge = build_bridge()
    result = bridge.run_agent(task="noop", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"
    assert RULES_MARKER in captured["context"].project_rules, (
        "the default composition stopped finding AGENTS.md"
    )


def test_explicit_working_dir_still_wins_over_the_process_cwd(roots, monkeypatch):
    """Injecting a loader must not change WHERE the search starts.

    A decoy under the process CWD must be ignored in favour of the explicitly
    passed working_dir, so an injected loader changes which loader runs, never
    which directory it starts from.
    """
    (roots.code_root / CUSTOM_RULES_FILE).write_text(f"# {RULES_MARKER}\n")
    (roots.process_cwd / CUSTOM_RULES_FILE).write_text("# decoy-from-process-cwd\n")
    captured = capture_run_context(monkeypatch)

    bridge = build_bridge(rules_loader=non_default_loader())
    result = bridge.run_agent(task="noop", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"
    rules = captured["context"].project_rules
    assert RULES_MARKER in rules
    assert "decoy-from-process-cwd" not in rules, (
        "the search started from the ambient CWD instead of the explicit working_dir"
    )


def test_bridge_rules_loader_is_appended_after_the_existing_final_parameter():
    """Old positional calls must be unaffected by the new dependency."""
    import inspect

    from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

    names = [
        n for n, p in inspect.signature(LangGraphBridge.__init__).parameters.items()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    assert names.index("rules_loader") > names.index("task_storage"), (
        "rules_loader must come after the previously final parameter"
    )


def test_runtime_wiring_passes_a_loader_to_the_bridge(roots, monkeypatch):
    """The production default is composed at RUNTIME WIRING, not in the bridge.

    Captures the real call so the composition point is evidenced rather than
    assumed.
    """
    from scrappy.cli.textual import langgraph_bridge as lgb
    from scrappy.cli.textual import runtime_wiring as rw

    captured = {}

    class Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    # runtime_wiring imports LangGraphBridge INSIDE the function, so the name
    # must be replaced at its defining module, not on runtime_wiring.
    monkeypatch.setattr(lgb, "LangGraphBridge", Recorder)

    app = Mock()
    app._path_provider = type("P", (), {"todo_file": lambda self: roots.storage_root / "TODO.md"})()
    app.bridge = Mock()

    injected = non_default_loader()
    rw.wire_textual_runtime(
        app=app,
        interactive_mode=Mock(),
        io=Mock(),
        orchestrator=StreamingModelBoundary(),
        output_adapter=Mock(),
        rules_loader=injected,
    )

    assert captured.get("rules_loader") is injected, (
        "runtime wiring did not forward the loader to the bridge"
    )
