import time

from termio_mcp.session import InteractiveSession
from termio_mcp.transport.pty import PtyTransport


def test_session_exec_expect_bash():
    transport = PtyTransport(command=["bash", "--norc", "--noprofile"])
    session = InteractiveSession(transport=transport)

    # Initial prompt synchronization
    session.expect(patterns=[r"[\$#]"], timeout=3.0, command="\n")

    # Execute a clean command
    res = session.exec_expect(command="echo 'TERMIO_SUCCESS'", timeout=3.0)
    assert isinstance(res, dict)
    assert res["success"] is True
    assert res["command"] == "echo 'TERMIO_SUCCESS'"
    assert "TERMIO_SUCCESS" in res["output"]

    # Verify history
    history = session.get_history(10)
    assert any("TERMIO_SUCCESS" in line for line in history)

    session.close()


def test_session_fast_exit_detection():
    # Spawning a command that terminates immediately
    transport = PtyTransport(command=["bash", "-c", "echo 'starting'; exit 42"])
    session = InteractiveSession(transport=transport)

    # Waiting for a pattern that will never arrive
    res = session.expect(patterns=[r"pattern_that_never_matches"], timeout=5.0)

    # Should detect process exit almost immediately without waiting 5 seconds
    assert res.get("matched") is False
    assert res.get("process_exited") is True
    assert res.get("exit_code") == 42
    assert "starting" in res.get("output", "")
    assert res.get("elapsed_seconds", 0) < 3.0

    session.close()


def test_session_poll_cmd():
    # Echoes back lines
    transport = PtyTransport(command=["cat"])
    session = InteractiveSession(transport=transport)

    # Expect a pattern while injecting spaces
    time.sleep(0.05)
    res = session.expect(
        patterns=[r"   "],
        poll_cmd=" ",
        poll_interval=0.05,
        timeout=2.0,
    )
    assert res.get("matched") is True
    session.close()


def test_session_exec_expect_timeout():
    """Test that exec_expect returns structured timeout result."""
    transport = PtyTransport(command=["cat"])  # cat never shows a shell prompt
    session = InteractiveSession(transport=transport)

    res = session.exec_expect(command="hello", timeout=1.0)
    assert isinstance(res, dict)
    assert res["success"] is False
    assert res["timeout"] is True
    assert "timed out" in res.get("error", "")

    session.close()


def test_session_exec_expect_process_exit():
    """Test that exec_expect returns structured result when process exits."""
    # Use a command that stays alive briefly then exits, so the write succeeds
    # but prompt is never matched
    transport = PtyTransport(command=["bash", "-c", "read line; exit 1"])
    session = InteractiveSession(transport=transport)
    time.sleep(0.1)  # Let bash start up

    res = session.exec_expect(command="trigger-exit", timeout=3.0)
    assert isinstance(res, dict)
    assert res["success"] is False
    assert res["process_exited"] is True

    session.close()


def test_session_close_joins_reader():
    """Test that close() joins the reader thread."""
    transport = PtyTransport(command=["cat"])
    session = InteractiveSession(transport=transport)
    assert session.reader_thread.is_alive()

    session.close()
    # After close, reader thread should have stopped
    assert not session.reader_thread.is_alive()
