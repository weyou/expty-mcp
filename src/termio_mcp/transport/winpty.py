import os
import shlex

from .base import BaseTransport

try:
    from winpty import PtyProcess as WinPtyProcess

    _WINPTY_AVAILABLE = True
except ImportError:
    WinPtyProcess = None
    _WINPTY_AVAILABLE = False


class WinPtyTransport(BaseTransport):
    """
    Windows ConPTY (Pseudo Console) transport using pywinpty.
    Provides native PTY emulation for cmd.exe, powershell.exe, ssh, and native Windows CLI tools.
    """

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        rows: int = 40,
        cols: int = 120,
    ):
        if not _WINPTY_AVAILABLE:
            raise RuntimeError(
                "pywinpty is not installed. Install it on Windows via 'pip install pywinpty'."
            )

        if isinstance(command, list):
            self.argv = command
            self.raw_command = " ".join(command)
        else:
            self.argv = shlex.split(command, posix=False)
            self.raw_command = command

        self.cwd = cwd
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        self.proc = WinPtyProcess.spawn(
            self.argv,
            cwd=self.cwd,
            env=merged_env,
            dimensions=(rows, cols),
        )
        self._closed = False

    def read(self, max_bytes: int = 4096) -> bytes:
        if self._closed or not self.proc.isalive():
            raise EOFError("Windows ConPTY process has terminated")

        try:
            # winpty PtyProcess.read() returns string
            text = self.proc.read(max_bytes)
            if not text:
                return b""
            return text.encode("utf-8", errors="replace")
        except EOFError:
            raise
        except Exception as e:
            if not self.proc.isalive():
                raise EOFError("Windows ConPTY process exited") from e
            raise

    def write(self, data: bytes) -> int:
        if self._closed or not self.proc.isalive():
            raise RuntimeError("Cannot write to terminated ConPTY process")

        text = data.decode("utf-8", errors="replace")
        self.proc.write(text)
        return len(data)

    def is_alive(self) -> bool:
        if self._closed:
            return False
        return self.proc.isalive()

    def get_exit_status(self) -> int | None:
        if self.proc.isalive():
            return None
        return self.proc.exitstatus

    def resize(self, rows: int, cols: int) -> None:
        """Dynamically resize ConPTY console dimensions."""
        if self.is_alive():
            try:
                self.proc.setwinsize(rows, cols)
            except Exception:
                pass

    def close(self, force: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.isalive():
                self.proc.terminate(force=force)
            self.proc.close()
        except Exception:
            pass

    @property
    def display_name(self) -> str:
        status = f"pid={self.proc.pid}" if self.is_alive() else "exited"
        return f"ConPTY[{self.raw_command}] ({status})"
