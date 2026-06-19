"""Mouse reporting policy adapter for Textual drivers."""

from __future__ import annotations

from collections.abc import Callable
import logging

logger = logging.getLogger(__name__)


class TextualMouseReportingPolicy:
    """Control terminal mouse reporting through Textual's active driver."""

    _DISABLE_SEQS = ("\x1b[?1000l", "\x1b[?1003l", "\x1b[?1015l", "\x1b[?1006l")

    def __init__(self, driver_provider: Callable[[], object | None]) -> None:
        self._driver_provider = driver_provider
        self._selection_mode = False

    @property
    def selection_mode(self) -> bool:
        return self._selection_mode

    def enable(self) -> None:
        if self._selection_mode:
            return
        self._call_driver("_enable_mouse_support")

    def disable_for_selection(self) -> None:
        self._selection_mode = True
        self._disable_reporting()

    def restore(self) -> None:
        self._selection_mode = False
        self._call_driver("_enable_mouse_support")

    def _call_driver(self, method_name: str) -> None:
        driver = self._driver_provider()
        fn = getattr(driver, method_name, None)
        if not callable(fn):
            logger.debug("mouse policy: driver lacks %s; skipping", method_name)
            return
        try:
            fn()
        except Exception as e:
            logger.debug("mouse policy: %s failed: %s", method_name, e)

    def _disable_reporting(self) -> None:
        driver = self._driver_provider()
        fn = getattr(driver, "_disable_mouse_support", None)
        if callable(fn):
            try:
                fn()
                return
            except Exception as e:
                logger.debug("mouse policy: _disable_mouse_support failed: %s", e)

        write = getattr(driver, "write", None)
        flush = getattr(driver, "flush", None)
        if callable(write):
            try:
                for seq in self._DISABLE_SEQS:
                    write(seq)
                if callable(flush):
                    flush()
                return
            except Exception as e:
                logger.debug("mouse policy: escape-seq disable failed: %s", e)

        logger.debug("mouse policy: no usable disable path; selection_mode set anyway")
