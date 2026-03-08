"""Tests for lazy exports from scrappy.cli.textual."""

from scrappy.cli import textual


def test_textual_package_exports_bridge_and_widgets():
    """Package root should lazily expose common Textual entry points."""
    from scrappy.cli.textual.bridge import ThreadSafeAsyncBridge
    from scrappy.cli.textual.status_components import PromptDisplay

    assert textual.ThreadSafeAsyncBridge is ThreadSafeAsyncBridge
    assert textual.PromptDisplay is PromptDisplay


def test_textual_package_exports_app():
    """Package root should lazily expose ScrappyApp."""
    from scrappy.cli.textual.app import ScrappyApp

    assert textual.ScrappyApp is ScrappyApp
