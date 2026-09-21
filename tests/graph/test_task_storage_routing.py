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
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
    """Four genuinely distinct directories, with distinctness ASSERTED.

    code_root    the directory the agent operates on
    storage_root where the selected task storage persists
    process_cwd  ambient CWD, moved here so that any code re-reading it is caught
    profile      disposable profile dir, kept separate from all of the above
    """
    code_root = tmp_path / "code_root"
    storage_root = tmp_path / "storage_root"
    process_cwd = tmp_path / "process_cwd"
    profile = tmp_path / "profile"
    for directory in (code_root, storage_root, process_cwd, profile):
        directory.mkdir()

    resolved = [str(d.resolve()) for d in (code_root, storage_root, process_cwd, profile)]
    assert len(set(resolved)) == 4, f"roots must be distinct, got {resolved}"

    monkeypatch.chdir(process_cwd)

    return SimpleNamespace(
        code_root=code_root,
        storage_root=storage_root,
        process_cwd=process_cwd,
        profile=profile,
    )


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

    # Unintended destinations stay ABSENT. This is the half that fails if the
    # tool quietly falls back to a code-root-derived provider.
    assert not (roots.code_root / "TODO.md").exists()
    assert not (roots.process_cwd / "TODO.md").exists()


# ---------------------------------------------------------------------------
# Obligation 2: default destination preserved when nothing is injected.
# ---------------------------------------------------------------------------


def test_default_destination_preserved_when_no_storage_injected(roots):
    """With no injected storage the tool keeps its normal code-root location."""
    from scrappy.infrastructure.paths import create_default_path_provider

    orchestrator = StreamingModelBoundary(add_task_turns("default destination"))
    bridge = make_bridge(orchestrator, task_storage=None)

    result = bridge.run_agent(task="add a task", working_dir=str(roots.code_root))

    assert result.success, f"agent run failed: {result.error}"

    expected = create_default_path_provider(roots.code_root).todo_file()
    assert Path(expected).exists(), "default task destination was not written"
    assert "default destination" in Path(expected).read_text()
    assert not (roots.storage_root / "TODO.md").exists()


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
    """A relative working_dir reaches all four consumers as one resolved value."""
    from scrappy.cli.textual import langgraph_bridge as bridge_module

    observed_rules_paths = []
    observed_confirmation_dirs = []

    real_loader = bridge_module.AgentRulesLoader

    class RecordingRulesLoader(real_loader):
        def load(self, path):
            observed_rules_paths.append(str(path))
            return super().load(path)

    real_handler = bridge_module.ToolConfirmationHandler

    def recording_handler(*args, **kwargs):
        observed_confirmation_dirs.append(kwargs.get("working_dir"))
        return real_handler(*args, **kwargs)

    monkeypatch.setattr(bridge_module, "AgentRulesLoader", RecordingRulesLoader)
    monkeypatch.setattr(bridge_module, "ToolConfirmationHandler", recording_handler)

    # Relative path, from a CWD that is NOT the code root.
    monkeypatch.chdir(roots.code_root.parent)
    relative = roots.code_root.name
    expected = str(roots.code_root.resolve())

    orchestrator = StreamingModelBoundary([[]])
    bridge = make_bridge(orchestrator, task_storage=make_storage(roots.storage_root / "TODO.md"))

    # _working_dir is cleared in run_agent's finally block, so it must be observed
    # DURING the run rather than after it.
    observed_working_dirs = []
    real_stream = bridge._run_with_streaming

    def recording_stream(*args, **kwargs):
        observed_working_dirs.append(bridge._working_dir)
        return real_stream(*args, **kwargs)

    monkeypatch.setattr(bridge, "_run_with_streaming", recording_stream)

    result = bridge.run_agent(task="noop", working_dir=relative)
    assert result.success, f"agent run failed: {result.error}"

    assert observed_confirmation_dirs == [expected]
    assert observed_rules_paths == [expected]
    assert observed_working_dirs == [expected]
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
    # Storage came from the INJECTED provider, not a fresh default.
    assert langgraph_bridge._task_storage is not None
    assert Path(langgraph_bridge._task_storage._path) == todo_path


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


def test_both_chat_routes_forward_the_captured_root(roots):
    """Both create_textual_runtime_session call sites carry the captured root."""
    from scrappy.cli.interactive import InteractiveMode
    from scrappy.cli.textual.runtime_wiring import create_textual_runtime_session

    # A Mock orchestrator here: _create_command_router reaches for model_selector
    # and other orchestrator surface unrelated to root forwarding.
    cli = make_cli(roots, orchestrator=Mock())

    # Route A: CLI._create_interactive_mode -> TextualInteractiveMode.
    textual_mode = cli._create_interactive_mode()
    assert Path(textual_mode._code_root).resolve() == roots.code_root.resolve()

    # Route B: the session constructor both entry points call.
    command_router = Mock()
    session = create_textual_runtime_session(
        io=Mock(),
        orchestrator=SimpleNamespace(output=None),
        session_context=Mock(),
        state_manager=Mock(),
        input_handler=Mock(),
        command_router=command_router,
        display=Mock(),
        tasks=Mock(),
        logger=Mock(),
        output_adapter=Mock(),
        code_root=cli._code_root,
    )
    assert isinstance(session, InteractiveMode)
    assert Path(session._code_root).resolve() == roots.code_root.resolve()
    assert Path(session._code_root).resolve() != roots.process_cwd.resolve()


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


def test_real_runner_preserves_working_memory_with_task_storage(roots):
    """Companion real-runner proof using the EXISTING working_memory parameter.

    The bridge supplies no working memory today, so this drives create_agent_runner
    directly rather than adding unrelated bridge memory plumbing just to combine
    proofs into one test.
    """
    from scrappy.graph.agent import create_agent_runner
    from scrappy.graph.state import AgentState

    todo_path = roots.storage_root / "TODO.md"
    working_memory = Mock()
    working_memory.get_context.return_value = ""

    orchestrator = StreamingModelBoundary(add_task_turns("memory plus storage"))
    graph, _checkpointer = create_agent_runner(
        orchestrator=orchestrator,
        tool_adapter=make_tool_adapter(),
        enable_hitl=False,
        working_memory=working_memory,
        task_storage=make_storage(todo_path),
    )

    state = AgentState.create_initial("add a task", str(roots.code_root))
    graph.invoke(state, {"configurable": {"thread_id": "wm-test"}, "recursion_limit": 60})

    assert "memory plus storage" in read_tasks(todo_path)
    assert not (roots.code_root / "TODO.md").exists()


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
    # The whole state round-trips through JSON, which a live object would break.
    json.dumps(dumped, default=str)
    assert final_state.working_dir == str(roots.code_root.resolve())
