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
    profile      a CONTROLLED DISPOSABLE profile, created here and BOUND to the
                 platform's home resolution, so it GOVERNS what the exercised
                 code actually sees rather than labelling a directory nothing
                 consumes
    """
    code_root = tmp_path / "code_root"
    storage_root = tmp_path / "storage_root"
    process_cwd = tmp_path / "process_cwd"
    profile = tmp_path / "profile"
    for directory in (code_root, storage_root, process_cwd, profile):
        directory.mkdir()

    # BIND the disposable profile to the platform's home resolution, through the
    # monkeypatch seam this fixture already uses. HOME is what POSIX consults;
    # USERPROFILE is what Windows consults. Binding BOTH makes every home lookup
    # under these tests land in the disposable profile, so this root governs the
    # exercised paths instead of merely being asserted distinct from them.
    # Binding the environment is NECESSARY BUT NOT SUFFICIENT on its own: the
    # production defaults also resolve through LEGACY_USER_DIR and
    # USER_CONFIG_FILE, which are bound AT IMPORT and so are already fixed
    # before this fixture runs, and Windows platform-directory discovery never
    # consults USERPROFILE. Those compositions are bound by INJECTING a
    # controlled provider, which is what `make_cli` now does.
    #
    # This also removes the defect behind PR53. The fixture previously read
    # os.environ["HOME"] UNCONDITIONALLY. HOME is POSIX-only and UNSET on
    # Windows, so the lookup raised KeyError during FIXTURE SETUP and ERRORED
    # all 18 nodes in this file; they never ran on Windows at all. Resolving to
    # the REAL profile instead would turn CI green while pointing this root at
    # the user's actual home, which inverts the containment intent.
    monkeypatch.setenv("HOME", str(profile))
    monkeypatch.setenv("USERPROFILE", str(profile))

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


def make_bridge(orchestrator, task_storage=None, rules_loader=None):
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
        rules_loader=rules_loader,
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

    from scrappy.context.agent_rules_loader import AgentRulesLoader as real_loader

    real_handler = bridge_module.ToolConfirmationHandler

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

    # Relative path, from a CWD that is NOT the code root.
    monkeypatch.chdir(roots.code_root.parent)
    relative = roots.code_root.name
    expected = str(roots.code_root.resolve())
    decoy_resolved = str(decoy.resolve())
    assert expected != decoy_resolved, "decoy must differ from the real code root"

    orchestrator = StreamingModelBoundary([[]])
    # PR-7: the bridge composes its loader ONCE at construction instead of
    # building one per run, so the recording loader is INJECTED here rather
    # than patched onto the module. What this test observes is unchanged: the
    # path handed to load(), and the CWD move performed mid-run.
    bridge = make_bridge(
        orchestrator,
        task_storage=make_storage(roots.storage_root / "tasks.md"),
        rules_loader=RecordingRulesLoader(),
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


def test_resolution_failure_does_not_strand_running_flag(roots, monkeypatch):
    """Resolution sits before the running flag, so a failure leaves it clear.

    The failure is INJECTED AT THE FILESYSTEM BOUNDARY rather than provoked by
    feeding a NUL byte in the path. A NUL path is not a portable way to make
    resolution fail: it raised on POSIX and on Windows CPython 3.11/3.12, but
    3.13 accepted it and returned normally, so the original form was measuring
    platform-specific string validation rather than the contract under test, and
    it failed on exactly one job (PR53 CI run 35673539588, Windows 3.13).

    Injecting OSError at Path.resolve exercises the SAME seam deterministically
    on every platform. Both original assertions are preserved: the exception
    still propagates, and the running flag must still be clear afterwards. The
    patch is narrowed to the path under test so unrelated resolution inside the
    run is untouched.
    """
    orchestrator = StreamingModelBoundary([[]])
    bridge = make_bridge(orchestrator)

    target = str(roots.code_root)
    real_resolve = Path.resolve

    def failing_resolve(self, *args, **kwargs):
        if str(self) == target:
            raise OSError("injected resolution failure")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failing_resolve)

    with pytest.raises(OSError):
        bridge.run_agent(task="noop", working_dir=target)

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
    """Build a real CLI rooted at code_root, with CWD already elsewhere.

    The provider and API key service are INJECTED, not defaulted. A bare
    construction here would select the production defaults, and those resolve
    through module attributes bound AT IMPORT (`LEGACY_USER_DIR`,
    `USER_CONFIG_FILE`) plus platform-directory discovery. Neither is redirected
    by setting HOME/USERPROFILE in the fixture, because both are already bound
    by the time the fixture runs, and Windows platform-directory lookup does not
    consult USERPROFILE at all. Injecting is what actually binds these
    compositions to the disposable profile.
    """
    from scrappy.cli.core import CLI
    from scrappy.infrastructure.paths import TempPathProvider
    from tests.cli.helpers import MockApiKeyConfigService

    os.chdir(roots.code_root)
    cli = CLI(
        orchestrator=orchestrator,
        io=Mock(),
        path_provider=TempPathProvider(roots.profile),
        api_key_service=MockApiKeyConfigService(),
    )
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

    The capture (`core.py:121`) and the default construction (`:128`) are
    ADJACENT statements inside one `__init__`, and the capture is itself a
    `Path.cwd()` reading. `make_cli` moves the CWD only AFTER construction, so
    under it "reuses the capture" and "takes a second Path.cwd() reading" return
    the identical value and the distinction is untestable: the assertions below
    would hold against either. This test therefore moves the process FOR REAL at
    that seam, so the two behaviours produce different directories.

    Each root carries a distinct marker file, so the destination is confirmed by
    reading what is actually on disk rather than by comparing path strings that
    a coincidence of layout could satisfy.

    REAL SCAN. The orchestrator is the PRODUCTION class built through the real
    OrchestratorFactory, so the CodebaseContext beneath it is the real one. The
    proof is that context's OWN scan result, read bidirectionally against two
    distinct marker files: the code-root marker present, the CWD decoy absent.
    Reading a marker from the captured constructor argument instead would only
    restate what the CLI passed, not where the default context actually looks.

    Stubbed ONLY at external boundaries: IO, the API key service, and semantic
    search, whose index service has no bearing on root capture.

    Storage uses the DISPOSABLE provider, which is the brief's prescribed
    composition for a routing test (isolation by construction). This is not a
    convenience. `OrchestratorFactory` calls `path_provider.ensure_user_dir()`
    (`factory.py:353`), and on a default-discovered provider that runs the
    LEGACY MIGRATION, which copies the seed into the platform data directory.
    That directory is inside the MEASURED profile region, so composing this
    test with `create_default_path_provider` re-creates the single
    `Library/Application Support/scrappy/command_history` escape that PR-4b
    eliminated. Measured, not predicted: it turned the escape set from 0 to 1.
    The disposable provider's `ensure_user_dir` only mkdirs under the injected
    temp dir (`paths.py:331-334`), and every member derives from it.
    """
    from scrappy.cli import core as core_module
    from scrappy.infrastructure.paths import TempPathProvider

    code_marker = "marker_code_root.py"
    decoy_marker = "marker_process_cwd.py"
    (roots.code_root / code_marker).write_text("# scanned when the capture is reused\n")
    (roots.process_cwd / decoy_marker).write_text("# scanned only if CWD is re-read\n")

    # External boundary. get_key is typed Optional[str], so the stub honours
    # that contract rather than returning a bare Mock the model layer rejects.
    api_key_service = Mock()
    api_key_service.get_key.return_value = "stub-api-key"

    real_orchestrator_cls = core_module.AgentOrchestrator
    captured = {}

    def recording_orchestrator(**kwargs):
        captured.update(kwargs)
        # Ambient CWD AT THE MOMENT OF CONSTRUCTION, to prove the move below
        # really had landed before the orchestrator was built.
        captured["ambient_cwd"] = os.getcwd()
        return real_orchestrator_cls(**{**kwargs, "enable_semantic_search": False})

    monkeypatch.setattr(core_module, "AgentOrchestrator", recording_orchestrator)

    # Move the process on the FIRST Path.cwd() reading, which is the capture
    # itself. A real os.chdir is used rather than a faked return value, so
    # anything re-reading the CWD by any means sees the moved directory.
    real_cwd = Path.cwd
    moved = []

    def cwd_then_move():
        here = real_cwd()
        if not moved:
            moved.append(True)
            os.chdir(roots.process_cwd)
        return here

    monkeypatch.setattr(Path, "cwd", staticmethod(cwd_then_move))

    os.chdir(roots.code_root)
    cli = core_module.CLI(
        orchestrator=None,
        io=Mock(),
        api_key_service=api_key_service,
        path_provider=TempPathProvider(roots.profile),
    )

    # ACTUAL EXERCISED CONSUMER, with a CHECKED disposable destination. The real
    # OrchestratorFactory calls path_provider.ensure_user_dir() (factory.py:353)
    # while building the components above, so this directory exists only because
    # production code ran. It proves the disposable profile GOVERNS a real user
    # level write rather than merely being asserted distinct, and it is the same
    # call that runs the legacy migration when the provider is default-resolved.
    user_dir = roots.profile / ".scrappy_user"
    assert user_dir.is_dir(), (
        "OrchestratorFactory.ensure_user_dir did not land in the disposable "
        f"profile; {user_dir} absent"
    )
    # The previous companion assertion here was VACUOUS: it allowed the case
    # Path.home() == roots.profile, which this fixture GUARANTEES, so the `or`
    # short-circuited and nothing could ever fail it. Replaced with a check that
    # can actually fail: the user-level write must not have landed in any of the
    # other three roots, which is where a misrouted provider would put it.
    for other in (roots.code_root, roots.storage_root, roots.process_cwd):
        assert not (other / ".scrappy_user").exists(), (
            f"user level write landed in the wrong root: {other}"
        )

    assert moved, "Path.cwd was never read, so the capture seam went unexercised"
    # The capture ran before the move and still holds the code root.
    assert Path(cli._code_root).resolve() == roots.code_root.resolve()
    # The CWD had genuinely moved by construction time, so a second reading
    # would have yielded a DIFFERENT directory than the capture.
    assert Path(captured["ambient_cwd"]).resolve() == roots.process_cwd.resolve()

    # THE PRIMARY PROOF, asserted FIRST so that it is the assertion a regression
    # trips: what the real default context actually SCANS, not what it was
    # handed. Bidirectional, so re-pointing the scan root fails either way.
    # Ordering matters here. The captured-argument check below would otherwise
    # short-circuit the run and this scan would never execute.
    context = cli.orchestrator.context
    context.explore()
    python_files = context.file_index.get("python", [])

    assert code_marker in python_files, (
        f"default context did not scan the captured code root; saw {python_files}"
    )
    assert decoy_marker not in python_files, (
        f"default context scanned the moved CWD instead; saw {python_files}"
    )

    # Corroborating only: the argument the CLI passed agrees with the scan.
    assert Path(captured["project_path"]).resolve() == roots.code_root.resolve()


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

    # Provider passed EXPLICITLY. A bare ScrappyApp selects the production
    # default, which resolves through import-bound module attributes the fixture
    # cannot reach. Reusing the CLI's own injected provider also keeps the app
    # and the CLI on ONE provider instead of two independently resolved ones.
    app = ScrappyApp(
        cli_factory=lambda: Mock(),
        api_key_service=MockApiKeyConfigService(),
        path_provider=cli._path_provider,
    )
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


# ---------------------------------------------------------------------------
# PR53 regression: the fixture must survive a MISSING ambient home.
# ---------------------------------------------------------------------------


@pytest.fixture
def no_ambient_home(monkeypatch):
    """Remove both ambient home variables BEFORE the `roots` fixture runs."""
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)


def test_missing_ambient_home_still_routes_to_the_disposable_profile(
    no_ambient_home, roots
):
    """PR53 regression, at the point that actually broke: FIXTURE SETUP.

    ORDERING IS THE PROOF. `no_ambient_home` is requested BEFORE `roots`, so
    pytest resolves it first and `roots` builds with no ambient home present.
    That is the Windows condition. Every contained baseline run has HOME
    assigned by the launcher, so without this test that path is exercised on no
    platform we measure, which is exactly how the original defect survived.

    A REAL consumer is then driven rather than Path.home() alone:
    OrchestratorFactory calls path_provider.ensure_user_dir() (factory.py:353),
    and the destination is CHECKED ON DISK, both positively and against the
    three other roots.
    """
    from scrappy.infrastructure.paths import TempPathProvider
    from scrappy.orchestrator.factory import OrchestratorFactory
    from tests.cli.helpers import MockApiKeyConfigService

    # The fixture rebound both variables despite neither existing beforehand.
    assert Path(os.environ["HOME"]).resolve() == roots.profile.resolve()
    assert Path(os.environ["USERPROFILE"]).resolve() == roots.profile.resolve()

    factory = OrchestratorFactory(
        project_path=str(roots.code_root),
        path_provider=TempPathProvider(roots.profile),
        enable_semantic_search=False,
        api_key_service=MockApiKeyConfigService(),
    )
    factory.create_all_components(task_history_recorder=lambda task: None)

    user_dir = roots.profile / ".scrappy_user"
    assert user_dir.is_dir(), (
        f"real consumer did not write to the disposable profile; {user_dir} absent"
    )
    for other in (roots.code_root, roots.storage_root, roots.process_cwd):
        assert not (other / ".scrappy_user").exists(), (
            f"user level write landed in the wrong root: {other}"
        )
