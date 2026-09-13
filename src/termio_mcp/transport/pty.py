import errno
import os
import select
import shlex

from ptyprocess import PtyProcess

from .base import BaseTransport


class PtyTransport(BaseTransport):
    """
    POSIX Pseudo-Terminal (PTY) transport for local commands, interactive shells,
    SSH sessions, REPLs, and container executions.
    """

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        rows: int = 40,
        cols: int = 120,
    ):
        if isinstance(command, str):
            self.argv = shlex.split(command)
            self.raw_command = command
        else:
            self.argv = list(command)
            self.raw_command = shlex.join(command)

        self.cwd = cwd
        # Prepare environment: inherit current os.environ, set TERM
        merged_env = os.environ.copy()
        merged_env["TERM"] = "xterm-256color"
        merged_env["COLUMNS"] = str(cols)
        merged_env["LINES"] = str(rows)
        if env:
            merged_env.update(env)

        self.proc = PtyProcess.spawn(
            argv=self.argv,
            cwd=self.cwd,
            env=merged_env,
            dimensions=(rows, cols),
        )
        self.fd = self.proc.fd
        self._closed = False

    def read(self, max_bytes: int = 4096, timeout: float = 0.05) -> bytes:
        data, _ = self.read_with_timestamp(max_bytes=max_bytes, timeout=timeout)
        return data

    def read_with_timestamp(
        self, max_bytes: int = 4096, timeout: float = 0.05
    ) -> tuple[bytes, float]:
        import time

        if self._closed or not self.proc.isalive():
            # Check if there are leftover bytes before raising EOF
            try:
                r, _, _ = select.select([self.fd], [], [], 0)
                if r:
                    data = os.read(self.fd, max_bytes)
                    return data, time.time()
            except Exception:
                pass
            raise EOFError("PTY process has terminated")

        try:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return b"", time.time()
            data = os.read(self.fd, max_bytes)
            return data, time.time()
        except OSError as e:
            # On Linux, reading from a closed PTY master returns EIO
            if e.errno == errno.EIO:
                raise EOFError("PTY master received EIO (child process exited)") from e
            raise

    def write(self, data: bytes) -> int:
        if self._closed or not self.proc.isalive():
            raise RuntimeError("Cannot write to terminated PTY process")
        return self.proc.write(data)

    def is_alive(self) -> bool:
        if self._closed:
            return False
        return self.proc.isalive()

    def get_exit_status(self) -> int | None:
        if self.proc.isalive():
            return None
        return self.proc.exitstatus

    def resize(self, rows: int, cols: int) -> None:
        """Dynamically resize the terminal dimensions."""
        if self.is_alive():
            self.proc.setwinsize(rows, cols)

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
        return f"PTY[{self.raw_command}] ({status})"
