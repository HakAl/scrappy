"""Behavioural proof that selected task storage travels the REAL execution route.

Scope. These tests drive the actual production chain

    LangGraphBridge.run_agent
        -> create_agent_runner
            -> _wrap_execute_node
                -> execute_node
                    -> _default_context_factory
                        -> TaskTool

with ONLY the streaming-model boundary stubbed. The runner, graph, execute node,
tool adapter and TaskTool are all real, and assertions read ACTUAL FILE CONTENT.
Supplying a dependency straight to ``execute_node`` would not prove the route and
is deliberately never the primary proof here.

Root separation is the point of the slice, so the fixture below asserts that the
code root, the storage root, the process CWD and the disposable profile are four
DISTINCT directories rather than merely arranging them to look separate.
"""

import json
import os
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scrappy.agent_tools.tools.base import ToolBase, ToolResult
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment


# ---------------------------------------------------------------------------
# Streaming boundary stub: the ONLY thing replaced on the primary route.
# ---------------------------------------------------------------------------


class StreamingModelBoundary:
    """Minimal stand-in for the orchestrator's streaming seam.

    Emits a prepared sequence of tool calls and then a plain completion. It
    implements ``stream_completion_with_fallback`` because that is the single
    method the think delegator calls; everything downstream of it stays real.
    """

    def __init__(self, tool_calls_per_turn):
        self._turns = list(tool_calls_per_turn)
        self._turn = 0
        self.calls = []

    def stream_completion_with_fallback(self, messages=None, selection_type=None, **kwargs):
        self.calls.append({"messages": messages, "selection_type": selection_type})
        tool_calls = self._turns[self._turn] if self._turn < len(self._turns) else []
        self._turn += 1

        fragments = [
            ToolCallFragment(
                id=f"call_{idx}",
                type="function",
                name=name,
                arguments=json.dumps(arguments),
                index=idx,
                complete=True,
            )
            for idx, (name, arguments) in enumerate(tool_calls)
        ]

        if not fragments:
            yield StreamChunk(
                content="All done.",
                model="stub-model",
                provider="stub",
                finish_reason="stop",
            )
            return

        yield StreamChunk(
            content="",
            tool_call_fragments=fragments,
            model="stub-model",
            provider="stub",
            finish_reason="stop",
        )


def add_task_turns(description):
    """One turn that adds a task via the real `task` tool, then one that stops."""
    return [[("task", {"command": "add", "description": description})], []]


# ---------------------------------------------------------------------------
# Four distinct roots.
# ---------------------------------------------------------------------------


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Four genuinely distinct roots, with distinctness ASSERTED.

    code_root    the directory the agent operates on
    storage_root where the selected task storage persists
    process_cwd  ambient CWD, moved here so that any code re-reading it is caught
    profile      the ACTUAL contained profile root this run is executing under,
                 taken from the launcher-assigned HOME rather than an invented
                 directory that nothing ever uses
    """
    code_root = tmp_path / "code_root"
    storage_root = tmp_path / "storage_root"
    process_cwd = tmp_path / "process_cwd"
    for directory in (code_root, storage_root, process_cwd):
        directory.mkdir()

    profile = Path(os.environ["HOME"])
    assert profile.is_dir(), "contained profile HOME should already exist"

    resolved = [str(d.resolve()) for d in (code_root, storage_root, process_cwd, profile)]
    assert len(set(resolved)) == 4, f"roots must be distinct, got {resolved}"

    monkeypatch.chdir(process_cwd)

    return SimpleNamespace(
        code_root=code_root,
        storage_root=storage_root,
        process_cwd=process_cwd,
        profile=profile,
    )


def default_todo(root):
    """The REAL default destination for a root, derived from the provider.

    The production provider returns ``<root>/.scrappy/.todo.md``. Guessing
    ``<root>/TODO.md`` would make every absence assertion vacuously true.
    """
    from scrappy.infrastructure.paths import create_default_path_provider

    return Path(create_default_path_provider(root).todo_file())


def make_storage(todo_path):
    """Real MarkdownTaskStorage at an explicit destination."""
    from scrappy.agent_tools.tools.task_tools import MarkdownTaskStorage

    return MarkdownTaskStorage(todo_path)


def make_tool_adapter():
    """Real tool adapter carrying the real TaskTool.

    NOTE, and this is a genuine property of the source, not a test convenience:
    ``task`` appears only in the ``full`` tool profile
    (agent_tools/registry_factory.py:46-76). The production default profile is
    ``optimized``, which does NOT register it. These tests therefore request
    ``full`` explicitly, because a route whose terminal tool is unregistered
    cannot be exercised at all.
    """
    from scrappy.graph.tools import ToolAdapter

    return ToolAdapter.create_default(profile="full")


def make_bridge(orchestrator, task_storage=None):
    """Construct a REAL LangGraphBridge with a real tool adapter.

    Only the app shell, the async bridge and the output adapter are doubles;
    those are UI transport, not part of the storage route under test.
    """
    from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

    app = Mock()
    async_bridge = Mock()
    # Confirmations auto-allow so the route runs unattended; the task tool is not
    # a destructive operation, this only removes the UI dependency.
    async_bridge.blocking_confirm_yna.return_value = "a"

    return LangGraphBridge(
        app=app,
        bridge=async_bridge,
        output_adapter=Mock(),
        orchestrator=orchestrator,
        tool_adapter=make_tool_adapter(),
        task_storage=task_storage,
    )


def read_tasks(todo_path):
    return todo_path.read_text() if todo_path.exists() else ""


# ---------------------------------------------------------------------------
# Obligation 1: the route persists under the INJECTED storage root.
# ---------------------------------------------------------------------------


def test_route_persists_under_injected_storage_root_not_code_root(roots):
    """Primary proof. Real chain, real file, both directions asserted."""
    todo_path = roots.storage_root / "TODO.md"
    orchestrator = StreamingModelBoundary(add_task_turns("routed through storage"))
    bridge = make_bridge(orchestrator, task_storage=make_storage(todo_path))

    result = bridge.run_agent(task="add a task", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"

    # Intended destination holds the real content.
    assert todo_path.exists(), "task was not persisted to the injected storage root"
    assert "routed through storage" in read_tasks(todo_path)

    # Unintended destinations stay ABSENT, derived from the REAL provider so the
    # assertion is not vacuous. This is the half that fails if the tool quietly
    # falls back to a code-root-derived provider.
    assert not default_todo(roots.code_root).exists()
    assert not default_todo(roots.process_cwd).exists()


# ---------------------------------------------------------------------------
# Obligation 2: default destination preserved when nothing is injected.
# ---------------------------------------------------------------------------


def test_default_destination_preserved_when_no_storage_injected(roots):
    """With no injected storage the tool keeps its normal code-root location."""
    orchestrator = StreamingModelBoundary(add_task_turns("default destination"))
    bridge = make_bridge(orchestrator, task_storage=None)

    result = bridge.run_agent(task="add a task", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"

    expected = default_todo(roots.code_root)
    assert expected.exists(), "default task destination was not written"
    assert "default destination" in expected.read_text()
    assert not default_todo(roots.storage_root).exists()
    assert not default_todo(roots.process_cwd).exists()


# ---------------------------------------------------------------------------
# Obligation 3: tier precedence, including a VALID BUT FALSEY storage.
# ---------------------------------------------------------------------------


def test_tool_level_storage_wins_over_context_storage(roots):
    """Explicit tool-level storage beats context storage, proven by file."""
    from scrappy.agent_tools.tools.base import ToolContext
    from scrappy.agent_tools.tools.task_tools import TaskTool

    tool_path = roots.storage_root / "TOOL.md"
    context_path = roots.storage_root / "CONTEXT.md"

    tool = TaskTool(storage=make_storage(tool_path))
    context = ToolContext(
        project_root=roots.code_root,
        task_storage=make_storage(context_path),
    )

    tool.execute(context, command="add", description="tool level wins")

    assert "tool level wins" in read_tasks(tool_path)
    assert not context_path.exists()


def test_falsey_injected_storage_still_wins(roots):
    """A valid storage that is falsey must not be discarded by truthiness.

    MarkdownTaskStorage defines no __bool__/__len__, so the regression is proven
    with an explicitly falsey storage object that is nonetheless a valid
    implementation. Under the old truthiness check this silently fell through to
    the context tier.
    """
    from scrappy.agent_tools.tools.base import ToolContext
    from scrappy.agent_tools.tools.task_tools import TaskTool

    tool_path = roots.storage_root / "FALSEY.md"
    context_path = roots.storage_root / "CONTEXT.md"

    class FalseyStorage:
        """Valid storage implementation that evaluates to False."""

        def __init__(self, inner):
            self._inner = inner

        def __bool__(self):
            return False

        def read_tasks(self):
            return self._inner.read_tasks()

        def write_tasks(self, tasks):
            return self._inner.write_tasks(tasks)

        def exists(self):
            return self._inner.exists()

        def clear(self):
            return self._inner.clear()

    tool = TaskTool(storage=FalseyStorage(make_storage(tool_path)))
    context = ToolContext(
        project_root=roots.code_root,
        task_storage=make_storage(context_path),
    )

    tool.execute(context, command="add", description="falsey but valid")

    assert "falsey but valid" in read_tasks(tool_path)
    assert not context_path.exists()


# ---------------------------------------------------------------------------
# Obligation 4: the bridge resolves ONCE and shares that value.
# ---------------------------------------------------------------------------


def test_relative_working_dir_resolved_once_and_shared(roots, monkeypatch):
    """A relative working_dir reaches ALL FOUR consumers as ONE resolved value.

    The CWD is deliberately MOVED mid-run, by the first consumer. A relative
    path resolved once at entry keeps its original meaning; any consumer that
    re-resolved it would now produce a different absolute path. Without that
    mid-run move, repeated resolution against an unchanged CWD would pass this
    test while being exactly the defect it is supposed to catch.
    """
    from scrappy.cli.textual import langgraph_bridge as bridge_module

    observed_rules_paths = []
    observed_confirmation_dirs = []
    observed_initial_roots = []
    observed_working_dirs = []

    # A decoy whose name matches code_root's, reachable from the second CWD.
    # If anything re-resolves the relative path after the move, it lands here.
    decoy_parent = roots.process_cwd / "decoy"
    decoy = decoy_parent / roots.code_root.name
    decoy.mkdir(parents=True)

    real_handler = bridge_module.ToolConfirmationHandler
    real_loader = bridge_module.AgentRulesLoader

    def recording_handler(*args, **kwargs):
        observed_confirmation_dirs.append(kwargs.get("working_dir"))
        return real_handler(*args, **kwargs)

    class RecordingRulesLoader(real_loader):
        def load(self, path):
            observed_rules_paths.append(str(path))
            # MOVE THE CWD mid-run, between consumers.
            os.chdir(decoy_parent)
            return super().load(path)

    monkeypatch.setattr(bridge_module, "ToolConfirmationHandler", recording_handler)
    monkeypatch.setattr(bridge_module, "AgentRulesLoader", RecordingRulesLoader)

    # Relative path, from a CWD that is NOT the code root.
    monkeypatch.chdir(roots.code_root.parent)
    relative = roots.code_root.name
    expected = str(roots.code_root.resolve())
    decoy_resolved = str(decoy.resolve())
    assert expected != decoy_resolved, "decoy must differ from the real code root"

    orchestrator = StreamingModelBoundary([[]])
    bridge = make_bridge(
        orchestrator, task_storage=make_storage(roots.storage_root / "tasks.md")
    )

    # _working_dir is cleared in run_agent's finally block, and the initial state
    # is consumed inside the run, so both are observed DURING the run.
    real_stream = bridge._run_with_streaming

    def recording_stream(graph, initial_state, *args, **kwargs):
        observed_initial_roots.append(initial_state.working_dir)
        observed_working_dirs.append(bridge._working_dir)
        return real_stream(graph, initial_state, *args, **kwargs)

    monkeypatch.setattr(bridge, "_run_with_streaming", recording_stream)

    result = bridge.run_agent(task="noop", working_dir=relative)
    assert result.success, f"agent run failed: {result.error}"

    # All four consumers, one value.
    assert observed_confirmation_dirs == [expected]
    assert observed_rules_paths == [expected]
    assert observed_initial_roots == [expected]
    assert observed_working_dirs == [expected]

    # Nothing drifted to the decoy, i.e. nothing re-resolved after the move.
    assert decoy_resolved not in observed_initial_roots
    assert decoy_resolved not in observed_working_dirs
    # It is the CODE root, never the storage root.
    assert expected != str(roots.storage_root.resolve())


def test_resolution_failure_does_not_strand_running_flag(roots):
    """Resolution sits before the running flag, so a failure leaves it clear."""
    orchestrator = StreamingModelBoundary([[]])
    bridge = make_bridge(orchestrator)

    with pytest.raises((OSError, ValueError)):
        bridge.run_agent(task="noop", working_dir="\x00invalid")

    assert bridge._is_running is False, "a failed resolution stranded _is_running"


# ---------------------------------------------------------------------------
# Obligation 5: cli=None with an injected app provider, through real wiring.
# ---------------------------------------------------------------------------


def test_wire_textual_runtime_composes_storage_from_injected_app_provider(roots):
    """cli=None must still honour an explicitly injected ScrappyApp provider.

    Drives the REAL wire_textual_runtime. Constructing the bridge directly would
    bypass exactly the composition decision under test.
    """
    from scrappy.cli.textual.runtime_wiring import wire_textual_runtime

    todo_path = roots.storage_root / "INJECTED.md"

    app = Mock()
    app.bridge = Mock()
    app._path_provider = SimpleNamespace(todo_file=lambda: todo_path)

    orchestrator = StreamingModelBoundary([[]])
    interactive_mode = Mock()
    io = Mock()

    langgraph_bridge = wire_textual_runtime(
        app=app,
        interactive_mode=interactive_mode,
        io=io,
        orchestrator=orchestrator,
        output_adapter=Mock(),
        cli=None,
        setup_wizard_callback=None,
    )

    assert langgraph_bridge is not None, "streaming orchestrator should wire a bridge"
    assert langgraph_bridge._task_storage is not None

    # Exercise the composed dependency for REAL through the real TaskTool, rather
    # than reading a private path attribute. The optimized production profile
    # omits `task`, so this composition proof drives the tool directly while the
    # full-profile tests above cover graph forwarding.
    from scrappy.agent_tools.tools.base import ToolContext
    from scrappy.agent_tools.tools.task_tools import TaskTool

    context = ToolContext(
        project_root=roots.code_root,
        task_storage=langgraph_bridge._task_storage,
    )
    TaskTool().execute(context, command="add", description="composed from injection")

    assert todo_path.exists(), "composed storage did not write to the injected path"
    assert "composed from injection" in todo_path.read_text()
    # Wrong destinations, derived from the real provider, stay absent.
    assert not default_todo(roots.code_root).exists()
    assert not default_todo(roots.process_cwd).exists()

    # And it reads back through the same composed dependency.
    assert any(
        "composed from injection" in t.description
        for t in langgraph_bridge._task_storage.read_tasks()
    )


# ---------------------------------------------------------------------------
# Obligation 6: the captured code root survives the complete route.
# ---------------------------------------------------------------------------


def make_cli(roots, orchestrator=None):
    """Build a real CLI rooted at code_root, with CWD already elsewhere."""
    from scrappy.cli.core import CLI

    os.chdir(roots.code_root)
    cli = CLI(orchestrator=orchestrator, io=Mock())
    # Move the process CWD AFTER composition. Nothing downstream may notice.
    os.chdir(roots.process_cwd)
    return cli


def test_captured_code_root_survives_injected_orchestrator_and_moved_cwd(roots):
    """Capture happens before orchestrator selection, so injection is covered."""
    injected = StreamingModelBoundary([[]])
    cli = make_cli(roots, orchestrator=injected)

    assert cli.orchestrator is injected, "injected orchestrator should be kept"
    assert Path(cli._code_root).resolve() == roots.code_root.resolve()
    assert Path(cli.agent_mgr._code_root).resolve() == roots.code_root.resolve()
    # Ambient CWD moved, and is NOT what the handler holds.
    assert Path(cli.agent_mgr._code_root).resolve() != roots.process_cwd.resolve()


def test_default_orchestrator_reuses_the_same_captured_root(roots, monkeypatch):
    """The default branch reuses the capture rather than re-reading CWD.

    AgentOrchestrator does not retain project_path as an attribute, so the
    construction seam is where reuse is observable. The orchestrator is also
    stubbed here to keep this test offline; building a real default one performs
    provider and model setup unrelated to root capture.
    """
    from scrappy.cli import core as core_module

    captured = {}

    def recording_orchestrator(**kwargs):
        captured.update(kwargs)
        return Mock()

    monkeypatch.setattr(core_module, "AgentOrchestrator", recording_orchestrator)

    cli = make_cli(roots, orchestrator=None)

    assert Path(cli._code_root).resolve() == roots.code_root.resolve()
    assert Path(captured["project_path"]).resolve() == roots.code_root.resolve()
    # Not the ambient CWD, which moved after composition.
    assert Path(captured["project_path"]).resolve() != roots.process_cwd.resolve()


def test_recreated_handler_reuses_captured_root_after_cwd_moved(roots):
    """reinitialize_handlers_with_bridge must not re-snapshot ambient CWD."""
    cli = make_cli(roots, orchestrator=StreamingModelBoundary([[]]))

    cli.reinitialize_handlers_with_bridge(Mock(), None)

    assert Path(cli.agent_mgr._code_root).resolve() == roots.code_root.resolve()
    assert Path(cli.agent_mgr._code_root).resolve() != roots.process_cwd.resolve()


class RecordingBridge:
    """Stands in for LangGraphBridge at the chat seam, recording the root used."""

    def __init__(self):
        self.working_dirs = []

    def run_agent(self, task, working_dir, tier=None):
        self.working_dirs.append(working_dir)
        return SimpleNamespace(
            success=True, cancelled=False, error=None, final_state=None
        )


def consume_chat(interactive_mode):
    """Drive the real chat consumption path and return the root it passed on."""
    bridge = RecordingBridge()
    interactive_mode.set_langgraph_bridge(bridge)
    interactive_mode._process_via_langgraph("hello")
    return bridge.working_dirs


def test_real_textual_interactive_run_forwards_and_consumes_captured_root(roots):
    """Route A: the ACTUAL TextualInteractiveMode.run call site.

    Only ScrappyApp is replaced, because launching the real TUI would block.
    create_textual_runtime_session and wire_textual_runtime are the real
    functions, so a production call site that stopped forwarding would be caught
    here. Consumption is then exercised with the CWD already moved.
    """
    from unittest.mock import patch

    cli = make_cli(roots, orchestrator=Mock())
    textual_mode = cli._create_interactive_mode()

    captured = {}
    real_session = None

    from scrappy.cli import textual_interactive as ti_module

    real_session_factory = ti_module.create_textual_runtime_session

    def recording_factory(**kwargs):
        captured.update(kwargs)
        nonlocal real_session
        real_session = real_session_factory(**kwargs)
        return real_session

    app = Mock()
    app.bridge = Mock()
    app._path_provider = SimpleNamespace(
        todo_file=lambda: roots.storage_root / "route_a.md"
    )

    with (
        patch.object(ti_module, "ScrappyApp", return_value=app),
        patch.object(ti_module, "create_textual_runtime_session", recording_factory),
    ):
        textual_mode.run()

    # The production call site supplied the captured root.
    assert Path(captured["code_root"]).resolve() == roots.code_root.resolve()
    # And the real InteractiveMode it built consumes exactly that root, with the
    # process CWD sitting somewhere else entirely.
    assert consume_chat(real_session) == [cli._code_root]
    assert Path(cli._code_root).resolve() != roots.process_cwd.resolve()


def test_real_app_setup_interactive_mode_forwards_and_consumes_captured_root(roots):
    """Route B: the ACTUAL ScrappyApp._setup_interactive_mode call site."""
    from unittest.mock import patch

    from scrappy.cli.textual import app as app_module
    from scrappy.cli.textual.app import ScrappyApp
    from tests.cli.helpers import MockApiKeyConfigService

    cli = make_cli(roots, orchestrator=Mock())

    app = ScrappyApp(cli_factory=lambda: Mock(), api_key_service=MockApiKeyConfigService())
    app._cli = cli
    app.output_adapter = Mock()

    captured = {}
    real_session = None
    real_session_factory = app_module.create_textual_runtime_session

    def recording_factory(**kwargs):
        captured.update(kwargs)
        nonlocal real_session
        real_session = real_session_factory(**kwargs)
        return real_session

    with (
        patch.object(app_module, "create_textual_runtime_session", recording_factory),
        patch.object(app_module, "wire_textual_runtime"),
    ):
        app._setup_interactive_mode()

    assert Path(captured["code_root"]).resolve() == roots.code_root.resolve()
    assert consume_chat(real_session) == [cli._code_root]
    assert Path(cli._code_root).resolve() != roots.process_cwd.resolve()


def test_agent_manager_consumes_captured_root_after_cwd_moved(roots):
    """The agent entry point consumes the captured root, not ambient CWD."""
    cli = make_cli(roots, orchestrator=Mock())
    cli.reinitialize_handlers_with_bridge(Mock(), None)

    bridge = RecordingBridge()
    cli.agent_mgr._langgraph_bridge = bridge
    cli.agent_mgr._run_langgraph_agent("do work", None, False, None)

    assert bridge.working_dirs == [cli._code_root]
    assert Path(bridge.working_dirs[0]).resolve() == roots.code_root.resolve()
    assert Path(bridge.working_dirs[0]).resolve() != roots.process_cwd.resolve()


def test_standalone_entry_snapshots_default_only_when_root_absent(roots):
    """A standalone component may default, but only with no explicit root."""
    from scrappy.cli.agent_manager import CLIAgentManager

    explicit = CLIAgentManager(Mock(), Mock(), code_root=str(roots.code_root))
    assert Path(explicit._code_root).resolve() == roots.code_root.resolve()

    defaulted = CLIAgentManager(Mock(), Mock())
    assert Path(defaulted._code_root).resolve() == roots.process_cwd.resolve()


# ---------------------------------------------------------------------------
# Obligation 7: existing propagation still reaches the tool context.
# ---------------------------------------------------------------------------


def test_default_factory_preserves_existing_propagation_alongside_storage(roots):
    """working_memory, run_context and semantic search survive the new argument."""
    from scrappy.graph.nodes.execute import _default_context_factory

    storage = make_storage(roots.storage_root / "TODO.md")
    working_memory = Mock()
    semantic = Mock()
    run_context = SimpleNamespace(semantic_search=semantic)

    context = _default_context_factory(
        str(roots.code_root),
        working_memory,
        run_context,
        task_storage=storage,
    )

    assert context.task_storage is storage
    assert context.run_context is run_context
    assert context.semantic_search is semantic
    assert context.orchestrator is not None, "working memory adapter was dropped"
    assert context.orchestrator.working_memory is working_memory
    assert Path(context.project_root) == roots.code_root


class ContextProbeTool(ToolBase):
    """Real registered tool that records the ToolContext it is handed.

    Observing at ACTUAL tool consumption is the point: asserting the default
    factory's return value in isolation would miss the graph wrappers, and
    asserting only that a task file appeared would still pass if working-memory
    forwarding were deleted.
    """

    def __init__(self, sink):
        self._sink = sink

    @property
    def name(self):
        return "context_probe"

    @property
    def description(self):
        return "Records the tool context for assertions."

    @property
    def parameters(self):
        return []

    def execute(self, context, **kwargs):
        self._sink.append(context)
        return ToolResult(success=True, output="recorded")


def test_real_route_consumes_memory_run_context_and_storage_together(roots):
    """All existing propagation is observed AT THE TOOL on the real route.

    Drives create_agent_runner directly because the bridge supplies no working
    memory today (langgraph_bridge.py:729); adding bridge memory plumbing purely
    to merge proofs would be unrelated scope.
    """
    from scrappy.graph.agent import create_agent_runner
    from scrappy.graph.state import AgentState

    todo_path = roots.storage_root / "tasks.md"
    storage = make_storage(todo_path)

    working_memory = Mock()
    working_memory.get_context.return_value = ""
    semantic = Mock()
    run_context = SimpleNamespace(
        semantic_search=semantic,
        is_cancelled=lambda: False,
        project_rules=None,
        reminder_manager=None,
        record_provider_success=lambda *a, **k: None,
    )

    seen = []
    adapter = make_tool_adapter()
    adapter._registry.register(ContextProbeTool(seen))

    orchestrator = StreamingModelBoundary(
        [
            [("context_probe", {}), ("task", {"command": "add", "description": "memory plus storage"})],
            [],
        ]
    )
    graph, checkpointer = create_agent_runner(
        orchestrator=orchestrator,
        tool_adapter=adapter,
        enable_hitl=False,
        working_memory=working_memory,
        task_storage=storage,
    )

    state = AgentState.create_initial("add a task", str(roots.code_root))
    config = {
        "configurable": {"thread_id": "wm-test", "run_context": run_context},
        "recursion_limit": 60,
    }
    graph.invoke(state, config)

    # Storage still routed.
    assert "memory plus storage" in read_tasks(todo_path)
    assert not default_todo(roots.code_root).exists()

    # And every existing dependency arrived at the tool, alongside storage.
    assert seen, "probe tool never ran; the route did not reach tool consumption"
    context = seen[0]
    assert context.task_storage is storage
    assert context.run_context is run_context
    assert context.semantic_search is semantic
    assert context.orchestrator is not None, "working memory forwarding was lost"
    assert context.orchestrator.working_memory is working_memory

    # Checkpointer evidence: the persisted state carries no live dependency.
    saved = list(checkpointer.list(config))
    assert saved, "no checkpoint was written on the real route"
    for item in saved:
        values = item.checkpoint.get("channel_values", {})
        assert "task_storage" not in values


# ---------------------------------------------------------------------------
# Obligation 8: custom factory keeps ownership.
# ---------------------------------------------------------------------------


def test_custom_factory_keeps_one_argument_contract_and_its_context(roots):
    """A caller factory is still called with ONE argument and used as returned.

    This holds even when task_storage was supplied separately: the caller owns
    what goes in its context, and the node must not rewrite it.
    """
    from scrappy.agent_tools.tools.base import ToolContext
    from scrappy.graph.nodes.execute import execute_node
    from scrappy.graph.state import AgentState, Message

    received_args = []
    caller_storage = make_storage(roots.storage_root / "CALLER.md")
    caller_context = ToolContext(project_root=roots.code_root, task_storage=caller_storage)

    def custom_factory(*args):
        received_args.append(args)
        return caller_context

    seen = {}

    class RecordingAdapter:
        def execute(self, tool_calls, context):
            seen["context"] = context
            return []

    state = AgentState.create_initial("t", str(roots.code_root))
    state = state.model_copy(
        update={
            "messages": [
                Message(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "1", "name": "task", "arguments": {"command": "list"}}],
                )
            ]
        }
    )

    execute_node(
        state,
        RecordingAdapter(),
        custom_factory,
        None,
        task_storage=make_storage(roots.storage_root / "IGNORED.md"),
    )

    assert received_args == [(str(roots.code_root),)], "factory contract changed"
    assert seen["context"] is caller_context, "returned context was not used as given"
    assert seen["context"].task_storage is caller_storage
    assert not (roots.storage_root / "IGNORED.md").exists()


# ---------------------------------------------------------------------------
# Obligation 9: nothing live is serialized into AgentState.
# ---------------------------------------------------------------------------


def test_no_live_storage_is_serialized_into_agent_state(roots):
    """Inspected on the route already under test; no alternate graph is built."""
    from scrappy.graph.state import AgentState

    storage = make_storage(roots.storage_root / "TODO.md")
    orchestrator = StreamingModelBoundary(add_task_turns("state stays serializable"))
    bridge = make_bridge(orchestrator, task_storage=storage)

    result = bridge.run_agent(task="add a task", working_dir=str(roots.code_root))
    assert result.success, f"agent run failed: {result.error}"

    final_state = result.final_state
    assert isinstance(final_state, AgentState)

    dumped = final_state.model_dump()
    assert "task_storage" not in dumped

    # STRICT serialization through the REAL pydantic path, with warnings
    # escalated to errors. Pydantic falls back with a warning when it meets a
    # type it cannot serialize, so simplefilter("error") is what makes this
    # strict. The earlier json.dumps(..., default=str) would have quietly
    # stringified a live object and let the defect through.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        payload = final_state.model_dump_json()
    reloaded = json.loads(payload)
    assert "task_storage" not in reloaded

    # Top-level fields specifically: none of them IS the live storage instance.
    # The strict serialization above is what carries the real proof; this is a
    # cheap direct check, not a deep scan.
    assert all(value is not storage for value in dumped.values())

    assert final_state.working_dir == str(roots.code_root.resolve())
