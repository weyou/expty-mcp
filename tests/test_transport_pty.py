import time

from expty_mcp.transport.pty import PtyTransport


def test_pty_transport_lifecycle():
    transport = PtyTransport(command=["echo", "termio-test-ok"])
    # Note: `echo` is transient and may exit before we check is_alive(),
    # so we skip the initial alive assertion and focus on output & exit status.
    time.sleep(0.2)

    # Read output
    output = b""
    try:
        while True:
            chunk = transport.read(1024, timeout=0.1)
            if not chunk:
                break
            output += chunk
    except EOFError:
        pass

    assert b"termio-test-ok" in output
    assert not transport.is_alive()
    assert transport.get_exit_status() == 0
    transport.close()


def test_pty_transport_interactive():
    transport = PtyTransport(command=["cat"])
    assert transport.is_alive()

    transport.write(b"ping-pong\n")
    time.sleep(0.1)
    chunk = transport.read(1024, timeout=0.2)
    assert b"ping-pong" in chunk

    transport.close(force=True)
    assert not transport.is_alive()
