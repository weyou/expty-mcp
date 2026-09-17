import time

from expty_mcp.server import (
    close_session,
    exec_expect,
    expect,
    get_history,
    read_buffer,
    send,
    spawn,
    status,
    switch_session,
)


def test_server_tool_aliases_and_routing():
    # 1. Spawn two sessions
    res1 = spawn(command="bash --norc", name="session-1")
    sid1 = res1["session_id"]

    res2 = spawn(command="bash --norc", name="session-2")
    sid2 = res2["session_id"]

    # Initial sync for both
    expect(patterns=[r"[\$#]\s*"], timeout=3.0, session_id=sid1)
    expect(expected_patterns=[r"[\$#]\s*"], timeout=3.0, session_id=sid2)

    # 2. Test send aliases (data, input, command) directly targeting sid1 without switch_session
    res_send1 = send(data="echo DATA_ALIAS\n", session_id=sid1)
    assert "Sent" in res_send1

    res_send2 = send(input="echo INPUT_ALIAS\n", session_id=sid1)
    assert "Sent" in res_send2

    res_send3 = send(command="echo CMD_ALIAS\n", session_id=sid1)
    assert "Sent" in res_send3

    # Check buffer of sid1
    time.sleep(0.1)
    buf1 = read_buffer(session_id=sid1)
    assert "DATA_ALIAS" in buf1
    assert "INPUT_ALIAS" in buf1
    assert "CMD_ALIAS" in buf1

    # 3. Test exec_expect with cmd & expected_patterns aliases and exit code probe on sid2
    res_exec = exec_expect(
        cmd="true",
        expected_patterns=[r"[\$#]\s*"],
        timeout=3.0,
        session_id=sid2,
        check_exit_code_cmd="echo $?",
    )
    assert res_exec["success"] is True
    assert res_exec["exit_code"] == 0

    # Non-zero exit code
    res_exec_fail = exec_expect(
        cmd="false",
        expected_patterns=[r"[\$#]\s*"],
        timeout=3.0,
        session_id=sid2,
        check_exit_code_cmd="echo $?",
    )
    assert res_exec_fail["success"] is True
    assert res_exec_fail["exit_code"] == 1

    # 4. Test interrupt_on_timeout via exec_expect on sid1
    res_intr = exec_expect(
        command="sleep 10",
        expected_patterns=[r"[\$#]\s*"],
        timeout=0.6,
        session_id=sid1,
        interrupt_on_timeout="\x03",
    )
    assert res_intr["success"] is False
    assert res_intr["timeout"] is True
    assert res_intr["interrupted"] is True
    assert res_intr["prompt_recovered"] is True

    # 5. Verify status and history routing directly with session_id
    stat = status(session_id=sid1)
    assert stat["session_id"] == sid1

    hist = get_history(limit=5, session_id=sid2)
    assert isinstance(hist, list)

    # 6. Test switch_session and active default behavior
    switch_res = switch_session(sid1)
    assert sid1 in switch_res

    # Cleanup
    close_session(session_id=sid1)
    close_session(session_id=sid2)
