import os
import sys

from .base import BaseTransport


def get_default_shell() -> str:
    """Return platform-native default interactive shell command."""
    if sys.platform == "win32":
        return "powershell.exe"
    return os.environ.get("SHELL", "bash")


def create_pty_transport(
    command: str | list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    rows: int = 40,
    cols: int = 120,
) -> BaseTransport:
    """
    Factory function to instantiate the optimal PTY transport for the host operating system.
    Uses WinPtyTransport (ConPTY) on Windows, and PtyTransport (ptyprocess) on Linux/macOS.
    """
    cmd = command if command is not None else get_default_shell()

    if sys.platform == "win32":
        from .winpty import WinPtyTransport

        return WinPtyTransport(command=cmd, cwd=cwd, env=env, rows=rows, cols=cols)

    from .pty import PtyTransport

    return PtyTransport(command=cmd, cwd=cwd, env=env, rows=rows, cols=cols)
