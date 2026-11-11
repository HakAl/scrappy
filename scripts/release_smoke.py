"""Fresh-install version and first-run Terms smoke, without provider credentials."""
from __future__ import annotations

import argparse
import codecs
import errno
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

# src/scrappy/orchestrator/provider_definitions.py / provider_catalog.py.
PROVIDER_ENV_NAMES = {"CEREBRAS_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "SAMBANOVA_API_KEY"}
ANSI = re.compile(r"\x1b(?:\][^\x07]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-_])")


def smoke_env(home: Path, binary: Path) -> dict[str, str]:
    home.mkdir()
    env = {
        "PATH": f"{binary.parent}:/usr/bin:/bin", "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_DATA_HOME": str(home / "data"), "HF_HOME": str(home / "models/hf"),
        "FASTEMBED_CACHE_PATH": str(home / "models/fastembed"),
        "LITELLM_LOCAL_MODEL_COST_MAP": "True", "PYTHON_DOTENV_DISABLED": "1",
        "LANG": "C.UTF-8", "TERM": "xterm-256color",
    }
    assert not PROVIDER_ENV_NAMES.intersection(env)
    return env


PROMPT = "Type 'ok' to continue, or 'q' to quit"


class VirtualScreen:
    """Minimal fail-closed cell model for the Terms composer."""

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], str] = {}
        self.cursor: tuple[int, int] | None = None
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.pending = ""

    def cell(self, position: tuple[int, int]) -> str:
        return self.cells.get(position, "")

    def prompt_position(self) -> tuple[int, int] | None:
        for row in sorted({r for r, _ in self.cells}):
            columns = [c for r, c in self.cells if r == row]
            start = min(columns)
            text = "".join(self.cell((row, c)) or " " for c in range(start, max(columns) + 1))
            offset = text.find(PROMPT)
            if offset >= 0:
                return row, start + offset
        return None

    def feed(self, data: bytes) -> None:
        text = self.pending + self.decoder.decode(data)
        self.pending = ""
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":
                begin = i
                if i + 1 == len(text):
                    self.pending = text[begin:]
                    break
                kind = text[i + 1]
                if kind == "[":
                    i += 2
                    while i < len(text) and not ("@" <= text[i] <= "~"):
                        i += 1
                    if i == len(text):
                        self.pending = text[begin:]
                        break
                    params, final = text[begin + 2:i], text[i]
                    if final in "JKXLMP@STr" or (params == "?1049" and final in "hl"):
                        self.cells.clear()
                        self.cursor = None
                    elif final in "Hf" and re.fullmatch(r"[0-9]*(;[0-9]*)?", params):
                        parts = params.split(";")
                        self.cursor = (int(parts[0] or 1), int(parts[1] or 1) if len(parts) > 1 else 1)
                    elif final in "mu" or (params.startswith("?") and final in "hlp"):
                        pass
                    else:
                        self.cursor = None
                elif kind == "]":
                    end = re.search(r"\x07|\x1b\\", text[i + 2:])
                    if end is None:
                        self.pending = text[begin:]
                        break
                    i = i + 2 + end.end() - 1
                else:
                    if kind == "c":
                        self.cells.clear()
                    self.cursor = None
                    i += 1
            elif self.cursor is not None:
                row, col = self.cursor
                if ch == "\r":
                    self.cursor = row, 1
                elif ch == "\n":
                    self.cursor = row + 1, col
                elif ch.isprintable():
                    self.cells[row, col] = ch
                    self.cursor = row, col + 1
            i += 1


def terms_smoke(
    binary: Path, cwd: Path, env: dict[str, str], *,
    ready_timeout: float = 90, quit_timeout: float = 30,
) -> dict[str, object]:
    import fcntl
    import pty
    import termios

    started = time.monotonic()
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(cwd)
            os.execve(binary, [str(binary)], env)
        except BaseException:
            os._exit(127)
    output = bytearray()
    screen = VirtualScreen()
    seen = False
    eof = False
    status: int | None = None
    position: tuple[int, int] | None = None
    phase = "READY"
    written = 0
    phases: list[dict[str, object]] = []

    def trace(name: str) -> None:
        phases.append({"name": name, "seconds": time.monotonic() - started, "bytes_written": written})

    trace(phase)
    deadline = started + ready_timeout
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        while time.monotonic() < deadline:
            if not eof and select.select([fd], [], [], min(0.05, max(0, deadline - time.monotonic())))[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    chunk = b""
                output.extend(chunk)
                screen.feed(chunk)
                seen = seen or "Terms of Use" in ANSI.sub("", output.decode(errors="replace"))
                if phase == "READY" and seen and (position := screen.prompt_position()) is not None:
                    deadline = time.monotonic() + quit_timeout
                    trace("TYPE")
                    written += os.write(fd, b"q")
                    phase = "ACK"
                    trace(phase)
                elif phase == "ACK" and position is not None and screen.cell(position) == "q":
                    trace("SUBMIT")
                    written += os.write(fd, b"\r")
                    phase = "EXIT"
                    trace(phase)
                if not chunk:
                    eof = True
            ended, child_status = os.waitpid(pid, os.WNOHANG)
            if ended:
                status = child_status
                break
            if eof:
                select.select([], [], [], min(0.01, max(0, deadline - time.monotonic())))
        if status is None:
            ended, child_status = os.waitpid(pid, os.WNOHANG)
            if ended:
                status = child_status
        if phase == "READY":
            raise RuntimeError("Terms prompt not ready")
        if phase == "ACK":
            raise RuntimeError("exited before q echo" if status is not None else "q not echoed")
        if status is None:
            raise RuntimeError("Terms quit timed out")
        code = os.waitstatus_to_exitcode(status)
        if not seen or code != 0:
            raise RuntimeError(f"Terms seen={seen}, exit={code}")
        return {"terms_seen": seen, "quit_exit": code, "phases": phases}
    except BaseException:
        print(json.dumps({"phases": phases}), file=sys.stderr)
        raise
    finally:
        if status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        os.close(fd)
        print(output.decode(errors="replace"), file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path)
    source.add_argument("--pypi")
    source.add_argument("--scrappy-bin", type=Path, help="local offline hook; skips install")
    parser.add_argument("--expect-version")
    args = parser.parse_args()
    expected = args.expect_version or args.pypi
    if expected is None or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", expected) is None:
        parser.error("--expect-version X.Y.Z is required for wheel/local smoke")
    try:
        with tempfile.TemporaryDirectory(prefix="scrappy-release-smoke-") as temp:
            root = Path(temp)
            if args.scrappy_bin:
                binary = args.scrappy_bin.resolve()
            else:
                venv_path = root / "venv"
                venv.EnvBuilder(with_pip=True).create(venv_path)
                target = str(args.wheel.resolve()) if args.wheel else f"scrappy-ai=={args.pypi}"
                subprocess.run([str(venv_path / "bin/python"), "-m", "pip", "--isolated", "install",
                                "--no-cache-dir", "--index-url", "https://pypi.org/simple", target],
                               check=True)
                binary = venv_path / "bin/scrappy"
            env = smoke_env(root / "home", binary)
            cwd = root / "cwd"
            cwd.mkdir()
            result = subprocess.run([str(binary), "version"], cwd=cwd, env=env,
                                    capture_output=True, text=True, check=True, timeout=60)
            print(result.stdout, end="", file=sys.stderr)
            print(result.stderr, end="", file=sys.stderr)
            if result.stdout.strip() != f"scrappy v{expected}":
                raise RuntimeError(f"version mismatch: expected scrappy v{expected}, got {result.stdout!r}")
            terms = terms_smoke(binary, cwd, env)
            cached = any(p.is_file() for p in (root / "home/models").rglob("*"))
            print(json.dumps({"ok": True, "version": expected, **terms, "model_cache_files": cached}))
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
