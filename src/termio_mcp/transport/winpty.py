import os
import queue
import shlex
import threading

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
        self._read_queue: queue.Queue[tuple[float, bytes] | None] = queue.Queue()
        self._reader_thread = threading.Thread(
            target=self._worker_loop,
            name=f"WinPtyReader-{self.proc.pid}",
            daemon=True,
        )
        self._reader_thread.start()

    def _worker_loop(self) -> None:
        """
        Dedicated background reader: pulls from blocking proc.read into queue
        with precise arrival timestamp.
        """
        import time

        while not self._closed:
            try:
                text = self.proc.read(4096)
                ts = time.time()
                if text:
                    self._read_queue.put((ts, text.encode("utf-8", errors="replace")))
                elif not self.proc.isalive():
                    break
            except Exception:
                break

        # Put EOF sentinel
        self._read_queue.put(None)

    def read(self, max_bytes: int = 4096, timeout: float = 0.1) -> bytes:
        data, _ = self.read_with_timestamp(max_bytes=max_bytes, timeout=timeout)
        return data

    def read_with_timestamp(
        self, max_bytes: int = 4096, timeout: float = 0.1
    ) -> tuple[bytes, float]:
        import time

        if self._closed:
            raise EOFError("Windows ConPTY process has been closed")

        try:
            item = self._read_queue.get(timeout=timeout)
            if item is None:
                raise EOFError("Windows ConPTY process has terminated")
            ts, data = item
            if len(data) > max_bytes:
                # Return prefix and push back remnant with same original timestamp
                prefix = data[:max_bytes]
                self._read_queue.put((ts, data[max_bytes:]))
                return prefix, ts
            return data, ts
        except queue.Empty:
            if not self.proc.isalive():
                raise EOFError("Windows ConPTY process has terminated")
            return b"", time.time()

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
        finally:
            try:
                self._reader_thread.join(timeout=0.5)
            except Exception:
                pass

    @property
    def display_name(self) -> str:
        status = f"pid={self.proc.pid}" if self.is_alive() else "exited"
        return f"ConPTY[{self.raw_command}] ({status})"
