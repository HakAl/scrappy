"""Fresh-install version and first-run Terms smoke, without provider credentials."""
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
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


def terms_smoke(binary: Path, cwd: Path, env: dict[str, str]) -> dict[str, object]:
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(binary, [str(binary)], env)
    output = bytearray()
    seen = False
    eof = False
    status: int | None = None
    deadline = time.monotonic() + 90
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        while time.monotonic() < deadline:
            if not eof and select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    chunk = b""
                output.extend(chunk)
                plain = ANSI.sub("", output.decode(errors="replace"))
                if not seen and "Terms of Use" in plain:
                    seen = True
                    os.write(fd, b"q\r")
                    deadline = time.monotonic() + 30
                if not chunk:
                    eof = True
            ended, child_status = os.waitpid(pid, os.WNOHANG)
            if ended:
                status = child_status
                break
            if eof:
                time.sleep(0.05)
        if status is None:
            ended, child_status = os.waitpid(pid, os.WNOHANG)
            if ended:
                status = child_status
        if status is None:
            raise RuntimeError("Terms startup/quit timed out")
        code = os.waitstatus_to_exitcode(status)
        if not seen or code != 0:
            raise RuntimeError(f"Terms seen={seen}, exit={code}")
        return {"terms_seen": seen, "quit_exit": code}
    finally:
        if status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        os.close(fd)
        # Preserve raw output for diagnosing startup failures, including model downloads.
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
