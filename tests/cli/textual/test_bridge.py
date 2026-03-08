"""Tests for ThreadSafeAsyncBridge."""

import threading
import time
from unittest.mock import Mock

import pytest

from scrappy.cli.textual.bridge import ThreadSafeAsyncBridge
from scrappy.cli.textual.messages import RequestInlineInput


def wait_for(condition, timeout: float = 1.0) -> None:
    """Poll until condition becomes true or fail."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for condition")


def test_blocking_prompt_posts_request_and_returns_result():
    """Worker-thread prompt should round-trip through provide_result."""
    app = Mock()
    requests: list[RequestInlineInput] = []
    app.post_message.side_effect = requests.append
    bridge = ThreadSafeAsyncBridge(app)
    result_holder: dict[str, str] = {}

    worker = threading.Thread(
        target=lambda: result_holder.setdefault("result", bridge.blocking_prompt("Name?", default="User"))
    )
    worker.start()

    wait_for(lambda: len(requests) == 1)
    request = requests[0]
    assert request.message == "Name?"
    assert request.input_type == "prompt"
    assert request.default == "User"

    bridge.provide_result(request.prompt_id, "Alice")
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert result_holder["result"] == "Alice"


def test_blocking_confirm_returns_false_on_shutdown():
    """Pending confirmations should fail closed when the bridge shuts down."""
    app = Mock()
    bridge = ThreadSafeAsyncBridge(app)
    result_holder: dict[str, bool] = {}

    worker = threading.Thread(
        target=lambda: result_holder.setdefault("result", bridge.blocking_confirm("Proceed?"))
    )
    worker.start()

    wait_for(lambda: app.post_message.called)
    bridge.shutdown()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert result_holder["result"] is False


def test_blocking_confirm_yna_normalizes_invalid_response():
    """Unexpected confirmation values should normalize to deny."""
    app = Mock()
    requests: list[RequestInlineInput] = []
    app.post_message.side_effect = requests.append
    bridge = ThreadSafeAsyncBridge(app)
    result_holder: dict[str, str] = {}

    worker = threading.Thread(
        target=lambda: result_holder.setdefault("result", bridge.blocking_confirm_yna("Allow?"))
    )
    worker.start()

    wait_for(lambda: len(requests) == 1)
    bridge.provide_result(requests[0].prompt_id, "maybe")
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert result_holder["result"] == "n"


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("blocking_prompt", {"message": "Name?", "default": ""}),
        ("blocking_confirm", {"question": "Proceed?"}),
        ("blocking_confirm_yna", {"question": "Allow?"}),
        ("blocking_checkpoint", {"message": "Checkpoint?", "default": "c"}),
    ],
)
def test_main_thread_calls_raise_runtime_error(method_name, kwargs):
    """Bridge calls from the main thread should fail fast to prevent deadlocks."""
    bridge = ThreadSafeAsyncBridge(Mock())
    method = getattr(bridge, method_name)

    with pytest.raises(RuntimeError, match="This will cause a deadlock"):
        method(**kwargs)
