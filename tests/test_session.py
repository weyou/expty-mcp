import time

from expty_mcp.session import InteractiveSession
from expty_mcp.transport.pty import PtyTransport


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


def test_session_history_timestamps_and_50ms_rule():
    """
    Test the 50ms inter-packet continuation rule:
    1. Pauses < 50ms merge into a single line, discarding the second timestamp.
    2. Pauses >= 50ms split into two lines, tagging the second with '↳ ' and its own timestamp.
    3. Ensure clean_buffer and raw_buffer remain 100% unpolluted.
    4. Ensure with_timestamps=False returns purely raw clean text.
    """
    from unittest.mock import MagicMock

    from expty_mcp.transport.base import BaseTransport

    mock_transport = MagicMock(spec=BaseTransport)
    mock_transport.is_alive.return_value = True
    mock_transport.read_with_timestamp.return_value = (b"", time.time())
    mock_transport.display_name = "mock"

    session = InteractiveSession(transport=mock_transport)

    t0 = 1000.0
    # Case 1: Packet A arriving at t0, incomplete line (no newline)
    session._append_data(b"Loading kernel modules...", timestamp=t0)

    # Case 1.1: Packet B arriving 20ms later (< 50ms), completes the line
    t1 = t0 + 0.02
    session._append_data(b" [OK]\n", timestamp=t1)

    # Case 2: Packet C arriving at t2, incomplete line
    t2 = t0 + 1.0
    session._append_data(b"Mounting rootfs...", timestamp=t2)

    # Case 2.1: Packet D arriving 80ms later (>= 50ms), delayed continuation
    t3 = t2 + 0.08
    session._append_data(b" done\n", timestamp=t3)

    # 1. Verify that buffers are 100% pure (no timestamps, no '↳')
    clean_buf = session.read_buffer()
    assert clean_buf == "Loading kernel modules... [OK]\nMounting rootfs... done\n"
    assert "↳" not in clean_buf
    assert "1000" not in clean_buf

    # 2. Verify with_timestamps=False (pure clean text lines)
    raw_history = session.get_history(limit=10, with_timestamps=False)
    assert raw_history == [
        "Loading kernel modules... [OK]",
        "Mounting rootfs...",
        "done",
    ]

    # 3. Verify with_timestamps=True (rendered formatting)
    rendered_history = session.get_history(limit=10, with_timestamps=True)
    assert len(rendered_history) == 3

    # First entry: merged < 50ms, timestamp is t0, no continuation prefix
    assert "Loading kernel modules... [OK]" in rendered_history[0]
    assert "↳" not in rendered_history[0]

    # Second entry: timestamp is t2, no continuation prefix
    assert "Mounting rootfs..." in rendered_history[1]
    assert "↳" not in rendered_history[1]

    # Third entry: split >= 50ms, timestamp is t3, WITH continuation prefix '↳ '
    assert "↳ done" in rendered_history[2]

    session.close()


def test_session_cross_chunk_backspace():
    from unittest.mock import MagicMock

    from expty_mcp.transport.base import BaseTransport

    mock_transport = MagicMock(spec=BaseTransport)
    mock_transport.is_alive.return_value = True
    mock_transport.read_with_timestamp.return_value = (b"", time.time())
    mock_transport.display_name = "mock"

    session = InteractiveSession(transport=mock_transport)

    # Chunk 1: "u"
    session._append_data(b"u")
    # Chunk 2: backspace and overwrite
    session._append_data(b"\buci show tinc\n")

    assert session.read_buffer() == "uci show tinc\n"
    raw_history = session.get_history(limit=5, with_timestamps=False)
    assert "uci show tinc" in raw_history

    session.close()




def test_session_exec_expect_interrupt_on_timeout():
    transport = PtyTransport(command=["bash", "--norc"])
    session = InteractiveSession(transport=transport)

    # Sync to initial prompt
    session.expect([r"[\$#]\s*"], timeout=3.0)

    # Run a blocking command and interrupt on timeout with \x03 (Ctrl+C)
    res = session.exec_expect(
        command="sleep 10",
        prompts=[r"[\$#]\s*"],
        timeout=0.8,
        interrupt_on_timeout="\x03",
    )

    assert res["success"] is False
    assert res["timeout"] is True
    assert res["interrupted"] is True
    assert res["prompt_recovered"] is True

    # Terminal should be recovered and ready for next command
    res2 = session.exec_expect(
        command="echo AFTER_INTERRUPT",
        prompts=[r"[\$#]\s*"],
        timeout=3.0,
    )
    assert res2["success"] is True
    assert "AFTER_INTERRUPT" in res2["output"]

    session.close()


def test_session_exec_expect_check_exit_code():
    transport = PtyTransport(command=["bash", "--norc"])
    session = InteractiveSession(transport=transport)

    # Sync to initial prompt
    session.expect([r"[\$#]\s*"], timeout=3.0)

    # Test exit code 0
    res_zero = session.exec_expect(
        command="true",
        prompts=[r"[\$#]\s*"],
        timeout=3.0,
        check_exit_code_cmd="echo $?",
    )
    assert res_zero["success"] is True
    assert res_zero["exit_code"] == 0

    # Test exit code 1
    res_one = session.exec_expect(
        command="false",
        prompts=[r"[\$#]\s*"],
        timeout=3.0,
        check_exit_code_cmd="echo $?",
    )
    assert res_one["success"] is True
    assert res_one["exit_code"] == 1

    session.close()
