import logging
import re
import threading
import time
from collections import deque
from typing import Any

from .pipeline import decode_escape_sequences, strip_ansi
from .transport.base import BaseTransport

logger = logging.getLogger(__name__)


class InteractiveSession:
    """
    Manages an active transport stream (PTY or Serial) with continuous background ingestion,
    thread-safe ring buffering, ANSI sanitization, and atomic Expect pattern matching.
    """

    def __init__(
        self,
        transport: BaseTransport,
        max_buffer: int = 65536,
        history_maxlen: int = 1000,
    ):
        self.transport = transport
        self.max_buffer = max_buffer
        self.lock = threading.Lock()
        self._stop_event = threading.Event()

        self.clean_buffer = ""
        self.raw_buffer = ""
        self.history: deque[str] = deque(maxlen=history_maxlen)
        self._truncation_count = 0
        self.last_error: str | None = None

        # Pending incomplete ANSI escape fragment from previous chunk
        self._ansi_pending = ""

        # Start continuous ingestion thread
        self.reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"Reader-{self.transport.display_name}",
            daemon=True,
        )
        self.reader_thread.start()

    def _reader_loop(self) -> None:
        """Continuously pull incoming bytes into memory without packet drops."""
        while not self._stop_event.is_set():
            try:
                if not self.transport.is_alive():
                    # Drain any remaining bytes before pausing
                    try:
                        chunk = self.transport.read(4096)
                        if chunk:
                            self._append_data(chunk)
                    except Exception:
                        pass
                    time.sleep(0.1)
                    continue

                chunk = self.transport.read(4096)
                if chunk:
                    self._append_data(chunk)
                else:
                    time.sleep(0.01)

            except EOFError:
                # Process exited or stream closed
                break
            except Exception as e:
                self.last_error = str(e)
                logger.debug("Reader loop exception: %s", e)
                time.sleep(0.05)

    def _append_data(self, raw_bytes: bytes) -> None:
        """Decode and append chunk to raw buffer, clean buffer, and line history."""
        raw_text = raw_bytes.decode("utf-8", errors="replace")

        with self.lock:
            # Use pending fragment from previous chunk to handle cross-chunk ANSI sequences
            clean_text, self._ansi_pending = strip_ansi(raw_text, self._ansi_pending)

            self.raw_buffer += raw_text
            self.clean_buffer += clean_text

            if len(self.clean_buffer) > self.max_buffer:
                self.clean_buffer = self.clean_buffer[-self.max_buffer :]
                self._truncation_count += 1

            if len(self.raw_buffer) > self.max_buffer:
                self.raw_buffer = self.raw_buffer[-self.max_buffer :]

            for line in clean_text.splitlines():
                stripped = line.strip()
                if stripped:
                    self.history.append(stripped)

    def write(self, data: bytes) -> int:
        """Write raw bytes directly to transport."""
        return self.transport.write(data)

    def send(self, text: str, send_enter: bool = False) -> int:
        """Send formatted text or escape sequences (e.g. \\\\x03 for Ctrl+C)."""
        encoded = decode_escape_sequences(text)
        if send_enter and not encoded.endswith(b"\r\n") and not encoded.endswith(b"\n"):
            encoded += b"\n"
        return self.write(encoded)

    def expect(
        self,
        patterns: str | list[str],
        timeout: float = 10.0,
        command: str | None = None,
        poll_cmd: str | None = None,
        poll_interval: float = 0.05,
    ) -> dict[str, Any]:
        """
        Atomically send an optional command and match incoming stream against patterns.
        """
        if isinstance(patterns, str):
            patterns = [patterns]

        compiled = [re.compile(p) for p in patterns]

        if command is not None:
            cmd_bytes = decode_escape_sequences(command)
            if not cmd_bytes.endswith(b"\n") and not cmd_bytes.endswith(b"\r"):
                cmd_bytes += b"\n"

            with self.lock:
                self.clean_buffer = ""
                self.raw_buffer = ""
                self.transport.write(cmd_bytes)

        start_time = time.time()
        last_poll = 0.0

        while (time.time() - start_time) < timeout:
            # Fast check: process termination
            if not self.transport.is_alive():
                # Allow a tiny grace window to ingest final EOF bytes
                time.sleep(0.05)
                with self.lock:
                    # Final match attempt on remaining buffer
                    for idx, pat in enumerate(compiled):
                        match = pat.search(self.clean_buffer)
                        if match:
                            return self._build_match_result(match, patterns[idx], start_time)

                    return {
                        "matched": False,
                        "process_exited": True,
                        "exit_code": self.transport.get_exit_status(),
                        "output": self.clean_buffer,
                        "elapsed_seconds": round(time.time() - start_time, 3),
                    }

            # Poll command injection (e.g. for bootloader interception)
            if poll_cmd is not None and (time.time() - last_poll) >= poll_interval:
                try:
                    self.send(poll_cmd)
                except Exception as e:
                    logger.debug("Failed to inject poll_cmd: %s", e)
                last_poll = time.time()

            # Pattern evaluation
            with self.lock:
                for idx, pat in enumerate(compiled):
                    match = pat.search(self.clean_buffer)
                    if match:
                        return self._build_match_result(match, patterns[idx], start_time)

            time.sleep(0.02)

        # Timeout reached
        with self.lock:
            return {
                "matched": False,
                "timeout": True,
                "output": self.clean_buffer,
                "elapsed_seconds": round(time.time() - start_time, 3),
            }

    def _build_match_result(
        self, match: re.Match, pattern: str, start_time: float
    ) -> dict[str, Any]:
        """Slice clean buffer and consume matched segment."""
        matched_str = match.group(0)
        start_pos = match.start()
        end_pos = match.end()

        before = self.clean_buffer[:start_pos]
        after = self.clean_buffer[end_pos:]

        # Consume buffer up to the end of the matched pattern
        self.clean_buffer = after

        return {
            "matched": True,
            "pattern": pattern,
            "match": matched_str,
            "before": before,
            "after": after,
            "output": before + matched_str,
            "elapsed_seconds": round(time.time() - start_time, 3),
        }

    def exec_expect(
        self,
        command: str,
        prompts: list[str] | None = None,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        """
        Execute a shell or REPL command, wait for prompt, and return structured result
        with clean stdout (prompt and local command echo removed).

        Returns a dict with keys:
            - success (bool): Whether the command completed and a prompt was matched.
            - output (str): Clean command output with echo and prompt stripped.
            - timeout (bool): True if the command timed out.
            - process_exited (bool): True if the process exited before matching.
            - exit_code (int | None): Process exit code if exited.
            - elapsed_seconds (float): Wall-clock time taken.
        """
        default_prompts = [
            r"[\$#]\s*$",
            r">>>\s*$",
            r"~ #",
            r"# $",
            r"login:\s*$",
            r"Password:\s*$",
        ]
        active_prompts = prompts if prompts else default_prompts
        res = self.expect(patterns=active_prompts, timeout=timeout, command=command)

        if res.get("matched"):
            output = res.get("before", "").strip()
            return {
                "success": True,
                "command": command,
                "output": output,
                "timeout": False,
                "process_exited": False,
                "exit_code": None,
                "elapsed_seconds": res.get("elapsed_seconds", 0),
            }

        if res.get("process_exited"):
            exit_code = res.get("exit_code")
            # For serial transports, exit_code is always None — show "disconnected"
            status_msg = (
                f"exit code {exit_code}" if exit_code is not None else "disconnected"
            )
            return {
                "success": False,
                "command": command,
                "output": res.get("output", ""),
                "timeout": False,
                "process_exited": True,
                "exit_code": exit_code,
                "error": f"Process terminated ({status_msg}) while waiting for prompt.",
                "elapsed_seconds": res.get("elapsed_seconds", 0),
            }

        return {
            "success": False,
            "command": command,
            "output": res.get("output", ""),
            "timeout": True,
            "process_exited": False,
            "exit_code": None,
            "error": f"Command timed out after {timeout}s waiting for prompt.",
            "elapsed_seconds": res.get("elapsed_seconds", 0),
        }

    def read_buffer(self, clear: bool = False) -> str:
        """Read accumulated text from buffer without blocking."""
        with self.lock:
            buf = self.clean_buffer
            if clear:
                self.clean_buffer = ""
            return buf

    def get_history(self, limit: int = 50) -> list[str]:
        """Fetch recent chronological line history."""
        with self.lock:
            return list(self.history)[-limit:]

    def close(self) -> None:
        """Stop background worker and close the underlying transport."""
        self._stop_event.set()
        try:
            self.transport.close()
        except Exception as e:
            logger.debug("Error closing transport: %s", e)
        # Wait for reader thread to exit gracefully
        try:
            self.reader_thread.join(timeout=1.0)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        """Diagnostic state."""
        return {
            "transport": self.transport.display_name,
            "alive": self.transport.is_alive(),
            "exit_status": self.transport.get_exit_status(),
            "reader_alive": self.reader_thread.is_alive(),
            "buffer_chars": len(self.clean_buffer),
            "history_lines": len(self.history),
            "truncations": self._truncation_count,
            "last_error": self.last_error,
        }
