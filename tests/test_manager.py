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
