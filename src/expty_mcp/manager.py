import datetime
import logging
import threading
import uuid
from typing import Any

from .session import InteractiveSession
from .transport import SerialTransport, create_pty_transport, get_default_shell

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
        self._spawn_lock = threading.Lock()

    def spawn_pty(
        self,
        command: str | list[str] | None = None,
        name: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        rows: int = 40,
        cols: int = 120,
    ) -> str:
        """Spawn a new local shell, command, or SSH connection within a platform-native PTY."""
        cmd = command if command is not None else get_default_shell()
        transport = create_pty_transport(command=cmd, cwd=cwd, env=env, rows=rows, cols=cols)
        session = InteractiveSession(transport=transport)

        session_id = f"pty-{uuid.uuid4().hex[:8]}"
        display_name = name or (cmd if isinstance(cmd, str) else " ".join(cmd))

        with self.lock:
            self.sessions[session_id] = session
            self.metadata[session_id] = {
                "id": session_id,
                "name": display_name,
                "type": "pty",
                "command": cmd,
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

        If a specific session_id is provided but does not exist, raises KeyError
        to prevent accidental command execution on the wrong session.
        If no session_id is provided and no sessions exist, auto-spawns a default shell.
        """
        need_spawn = False

        with self.lock:
            # Case 1: Explicit session_id was provided — strict lookup, never fallback
            if session_id is not None:
                if session_id in self.sessions:
                    return session_id, self.sessions[session_id]
                raise KeyError(
                    f"Session '{session_id}' not found. "
                    f"Available sessions: {list(self.sessions.keys())}"
                )

            # Case 2: No session_id provided — resolve to active session
            if self.active_session_id and self.active_session_id in self.sessions:
                return self.active_session_id, self.sessions[self.active_session_id]

            # If only 1 session exists, auto-select it
            if len(self.sessions) == 1:
                single_id = next(iter(self.sessions.keys()))
                self.active_session_id = single_id
                return single_id, self.sessions[single_id]

            # If multiple sessions exist but none is active, raise an error
            if self.sessions:
                raise KeyError(
                    "No active session set and multiple sessions exist. "
                    f"Please specify a session_id. Available: {list(self.sessions.keys())}"
                )

            # Case 3: No sessions at all — auto-spawn default shell
            need_spawn = True

        if need_spawn:
            with self._spawn_lock:
                # Double-check: another thread might have spawned while we waited
                with self.lock:
                    if self.active_session_id and self.active_session_id in self.sessions:
                        return self.active_session_id, self.sessions[self.active_session_id]
                    if len(self.sessions) == 1:
                        single_id = next(iter(self.sessions.keys()))
                        self.active_session_id = single_id
                        return single_id, self.sessions[single_id]

                default_shell = get_default_shell()
                logger.info(
                    "No active session found; auto-spawning default '%s' session.", default_shell
                )
                new_id = self.spawn_pty(command=default_shell, name="default-shell")
                with self.lock:
                    return new_id, self.sessions[new_id]

        # Should not reach here, but safety fallback
        raise KeyError("No sessions available.")

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
