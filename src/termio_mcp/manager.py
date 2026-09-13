import datetime
import logging
import threading
import uuid
from typing import Any

from .session import InteractiveSession
from .transport.pty import PtyTransport
from .transport.serial import SerialTransport

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages multiple concurrent interactive sessions (PTY processes, SSH, Serial devices).
    Provides automatic resolution of active session when session_id is omitted.
    """

    def __init__(self):
        self.sessions: dict[str, InteractiveSession] = {}
        self.metadata: dict[str, dict[str, Any]] = {}
        self.active_session_id: str | None = None
        self.lock = threading.Lock()

    def spawn_pty(
        self,
        command: str = "bash",
        name: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        rows: int = 40,
        cols: int = 120,
    ) -> str:
        """Spawn a new local shell, command, or SSH connection within a PTY."""
        transport = PtyTransport(command=command, cwd=cwd, env=env, rows=rows, cols=cols)
        session = InteractiveSession(transport=transport)

        session_id = f"pty-{uuid.uuid4().hex[:8]}"
        display_name = name or (command if isinstance(command, str) else " ".join(command))

        with self.lock:
            self.sessions[session_id] = session
            self.metadata[session_id] = {
                "id": session_id,
                "name": display_name,
                "type": "pty",
                "command": command,
                "created_at": datetime.datetime.now().isoformat(),
            }
            self.active_session_id = session_id

        return session_id

    def spawn_serial(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        name: str | None = None,
    ) -> str:
        """Connect to a physical or virtual serial port."""
        transport = SerialTransport(port=port, baudrate=baudrate)
        session = InteractiveSession(transport=transport)

        session_id = f"serial-{uuid.uuid4().hex[:8]}"
        display_name = name or f"{port}@{baudrate}"

        with self.lock:
            self.sessions[session_id] = session
            self.metadata[session_id] = {
                "id": session_id,
                "name": display_name,
                "type": "serial",
                "port": port,
                "baudrate": baudrate,
                "created_at": datetime.datetime.now().isoformat(),
            }
            self.active_session_id = session_id

        return session_id

    def get_session(self, session_id: str | None = None) -> tuple[str, InteractiveSession]:
        """
        Retrieve session by session_id, or resolve to active_session_id.
        If no session exists, automatically spawns a default 'bash' PTY session.
        """
        with self.lock:
            target_id = session_id or self.active_session_id

            if target_id and target_id in self.sessions:
                return target_id, self.sessions[target_id]

            # If only 1 session exists, select it
            if len(self.sessions) == 1:
                single_id = next(iter(self.sessions.keys()))
                self.active_session_id = single_id
                return single_id, self.sessions[single_id]

            # Auto-spawn default session if empty
            if not self.sessions:
                logger.info("No active session found; auto-spawning default 'bash' session.")

        # Release lock before spawning to avoid deadlock
        new_id = self.spawn_pty(command="bash", name="default-bash")
        with self.lock:
            return new_id, self.sessions[new_id]

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all managed sessions with runtime health status."""
        results = []
        with self.lock:
            for sid, sess in self.sessions.items():
                meta = self.metadata.get(sid, {}).copy()
                meta["active"] = sid == self.active_session_id
                meta["alive"] = sess.transport.is_alive()
                meta["display"] = sess.transport.display_name
                results.append(meta)
        return results

    def switch_session(self, session_id: str) -> bool:
        """Switch the current active session."""
        with self.lock:
            if session_id in self.sessions:
                self.active_session_id = session_id
                return True
            return False

    def close_session(self, session_id: str | None = None) -> bool:
        """Close and clean up a target session."""
        with self.lock:
            target_id = session_id or self.active_session_id
            if not target_id or target_id not in self.sessions:
                return False

            sess = self.sessions.pop(target_id)
            self.metadata.pop(target_id, None)

            if self.active_session_id == target_id:
                self.active_session_id = next(iter(self.sessions.keys())) if self.sessions else None

        sess.close()
        return True

    def close_all(self) -> None:
        """Clean up all active sessions on shutdown."""
        with self.lock:
            to_close = list(self.sessions.values())
            self.sessions.clear()
            self.metadata.clear()
            self.active_session_id = None

        for sess in to_close:
            try:
                sess.close()
            except Exception:
                pass
