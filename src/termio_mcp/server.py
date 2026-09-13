import atexit
import logging
from typing import Any

try:
    # MCP SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        # MCP SDK 1.x
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        # Standalone fastmcp package
        from fastmcp import FastMCP

from .manager import SessionManager
from .transport.serial import list_serial_ports

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP(
    name="termio-mcp",
    instructions=(
        "Universal interactive PTY and Serial stream manager for AI agents. "
        "Supports persistent SSH sessions, local shells, REPLs, hardware UARTs, "
        "and atomic Expect state-machine matching with zero byte-loss."
    ),
)

# Global session manager instance
manager = SessionManager()
atexit.register(manager.close_all)


@mcp.tool()
def termio_spawn(
    command: str = "bash",
    name: str | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    rows: int = 40,
    cols: int = 120,
) -> dict[str, Any]:
    """
    Spawn a new persistent interactive process (bash, ssh, python, gdb, docker, etc.) in a PTY.

    Args:
        command: Command string or binary to execute (e.g. 'bash', 'ssh user@192.168.1.1').
        name: Optional friendly name for this session (e.g. 'router-ssh').
        cwd: Optional working directory.
        env: Optional environment variables dictionary.
        rows: Terminal rows (default: 40).
        cols: Terminal columns (default: 120).
    """
    sid = manager.spawn_pty(command=command, name=name, cwd=cwd, env=env, rows=rows, cols=cols)
    return {
        "success": True,
        "session_id": sid,
        "name": name or command,
        "command": command,
        "message": f"Spawned PTY session '{sid}' running: {command}",
    }


@mcp.tool()
def termio_serial(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 115200,
    name: str | None = None,
) -> dict[str, Any]:
    """
    Connect to a hardware or virtual serial device (UART / router console / microcontroller).

    Args:
        port: Serial device path (e.g. '/dev/ttyUSB0', 'COM3').
        baudrate: Baud rate (e.g. 115200, 9600, 57600).
        name: Optional friendly name for this session.
    """
    sid = manager.spawn_serial(port=port, baudrate=baudrate, name=name)
    return {
        "success": True,
        "session_id": sid,
        "port": port,
        "baudrate": baudrate,
        "message": f"Opened Serial session '{sid}' on {port}@{baudrate}",
    }


@mcp.tool()
def termio_list_ports() -> list[dict[str, Any]]:
    """Enumerate attached physical and virtual serial ports on the host."""
    return list_serial_ports()


@mcp.tool()
def termio_exec_expect(
    command: str,
    prompts: list[str] | None = None,
    timeout: float = 8.0,
    session_id: str | None = None,
) -> str:
    """
    Execute a shell, REPL, or bootloader command and automatically wait for prompt to return.
    Strips command echo and ANSI formatting, returning clean stdout in a single tool call.

    Args:
        command: The command line to execute.
        prompts: Optional list of prompt patterns (defaults to standard shell and REPL prompts).
        timeout: Maximum seconds to wait for the prompt to return.
        session_id: Target session ID (defaults to currently active session).
    """
    _, sess = manager.get_session(session_id)
    return sess.exec_expect(command=command, prompts=prompts, timeout=timeout)


@mcp.tool()
def termio_expect(
    patterns: list[str],
    command: str | None = None,
    timeout: float = 10.0,
    poll_cmd: str | None = None,
    poll_interval: float = 0.05,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Atomically send an optional command and match incoming stream against prompt patterns.
    Ideal for multi-step authentication (SSH login/password), prompts, and U-Boot interception.

    Args:
        patterns: List of regex/substring patterns to expect (e.g. ['password:', '# ']).
        command: Optional command/response to send before waiting.
        timeout: Maximum seconds to wait. Defaults to 10.0s.
        poll_cmd: Characters to repeatedly send during wait (e.g. ' ' for autoboot intercept).
        poll_interval: Interval between repeating poll_cmd. Defaults to 0.05s.
        session_id: Target session ID (defaults to currently active session).
    """
    _, sess = manager.get_session(session_id)
    return sess.expect(
        patterns=patterns,
        timeout=timeout,
        command=command,
        poll_cmd=poll_cmd,
        poll_interval=poll_interval,
    )


@mcp.tool()
def termio_send(
    text: str,
    send_enter: bool = False,
    session_id: str | None = None,
) -> str:
    """
    Send raw characters or escape sequences (e.g. '\\x03' for Ctrl+C, '\\x1b' for Escape, spaces).

    Args:
        text: Raw text or escape sequence string.
        send_enter: If True, appends a newline.
        session_id: Target session ID (defaults to currently active session).
    """
    sid, sess = manager.get_session(session_id)
    bytes_sent = sess.send(text=text, send_enter=send_enter)
    return f"Sent {bytes_sent} bytes to session '{sid}'."


@mcp.tool()
def termio_read_buffer(
    clear: bool = False,
    session_id: str | None = None,
) -> str:
    """
    Read newly accumulated text from the stream buffer without blocking.

    Args:
        clear: If True, flushes the read buffer after fetching.
        session_id: Target session ID (defaults to currently active session).
    """
    _, sess = manager.get_session(session_id)
    buf = sess.read_buffer(clear=clear)
    return buf if buf else "(Buffer is currently empty)"


@mcp.tool()
def termio_get_history(
    limit: int = 50,
    session_id: str | None = None,
) -> list[str]:
    """
    Retrieve recent chronological line history captured by the background daemon.

    Args:
        limit: Number of recent lines to retrieve (default: 50).
        session_id: Target session ID (defaults to currently active session).
    """
    _, sess = manager.get_session(session_id)
    return sess.get_history(limit=limit)


@mcp.tool()
def termio_list_sessions() -> list[dict[str, Any]]:
    """List all active PTY and Serial sessions with runtime health status."""
    return manager.list_sessions()


@mcp.tool()
def termio_switch_session(session_id: str) -> str:
    """
    Switch the default active session.

    Args:
        session_id: Target session ID to make active.
    """
    if manager.switch_session(session_id):
        return f"Active session switched to '{session_id}'."
    return f"Error: Session '{session_id}' not found."


@mcp.tool()
def termio_close_session(session_id: str | None = None) -> str:
    """
    Close and terminate an interactive session.

    Args:
        session_id: Target session ID to close (defaults to active session).
    """
    target = session_id or manager.active_session_id
    if manager.close_session(session_id):
        return f"Session '{target}' successfully closed."
    return f"Error: Session '{target}' not found."


@mcp.tool()
def termio_status(session_id: str | None = None) -> dict[str, Any]:
    """
    Check connection health, buffer statistics, and background daemon status.

    Args:
        session_id: Target session ID (defaults to active session).
    """
    sid, sess = manager.get_session(session_id)
    res = sess.status()
    res["session_id"] = sid
    return res


def main():
    """CLI Entrypoint for running termio-mcp server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
