import pytest

from termio_mcp.manager import SessionManager


def test_manager_lifecycle():
    manager = SessionManager()

    # Spawn session A
    sid_a = manager.spawn_pty(command=["bash", "--norc"], name="sess-a")
    assert sid_a in manager.sessions
    assert manager.active_session_id == sid_a

    # Spawn session B
    sid_b = manager.spawn_pty(command=["python3", "-q"], name="sess-b")
    assert sid_b in manager.sessions
    assert manager.active_session_id == sid_b

    # List sessions
    sessions = manager.list_sessions()
    assert len(sessions) == 2
    assert any(s["id"] == sid_a for s in sessions)
    assert any(s["id"] == sid_b for s in sessions)

    # Switch session
    assert manager.switch_session(sid_a) is True
    assert manager.active_session_id == sid_a

    # Get active session
    resolved_id, sess = manager.get_session()
    assert resolved_id == sid_a
    assert sess.transport.is_alive()

    # Close session A
    assert manager.close_session(sid_a) is True
    assert sid_a not in manager.sessions
    assert manager.active_session_id == sid_b

    # Close all
    manager.close_all()
    assert len(manager.sessions) == 0


def test_manager_invalid_session_id_raises():
    """Test that providing an invalid session_id raises KeyError instead of falling back."""
    manager = SessionManager()

    # Spawn a session so there's an active one
    sid = manager.spawn_pty(command=["bash", "--norc"], name="test")

    # Requesting a non-existent session ID should raise KeyError
    with pytest.raises(KeyError, match="not found"):
        manager.get_session("nonexistent-id-12345")

    # But requesting without session_id should resolve to the active session
    resolved_id, sess = manager.get_session()
    assert resolved_id == sid

    manager.close_all()


def test_manager_no_active_multiple_sessions_raises():
    """Test that having multiple sessions but no active raises KeyError."""
    manager = SessionManager()

    _sid_a = manager.spawn_pty(command=["bash", "--norc"], name="a")
    _sid_b = manager.spawn_pty(command=["bash", "--norc"], name="b")

    # Manually unset active session to simulate stale state
    with manager.lock:
        manager.active_session_id = None

    with pytest.raises(KeyError, match="multiple sessions exist"):
        manager.get_session()

    manager.close_all()


def test_manager_concurrent_get_session_auto_spawn():
    """Test that concurrent get_session() calls on an empty manager spawn exactly one session."""
    import concurrent.futures

    manager = SessionManager()
    results = []

    def _call_get_session():
        sid, _ = manager.get_session()
        return sid

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_call_get_session) for _ in range(8)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # All threads must receive the exact same session_id
    assert len(set(results)) == 1
    # Exactly one session must exist in the manager
    assert len(manager.sessions) == 1

    manager.close_all()
