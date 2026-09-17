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
    name="expty",
    instructions=(
        "Interactive PTY/Serial stream manager. Prefer over direct shell commands "
        "for multi-turn or interactive operations via SSH, UART/serial, or Telnet "
        "to preserve state and handle prompts."
    ),
)

# Global session manager instance
manager = SessionManager()
atexit.register(manager.close_all)


@mcp.tool()
def spawn(
    command: str | None = None,
    name: str | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    rows: int = 40,
    cols: int = 120,
) -> dict[str, Any]:
    """
    Spawn a new persistent interactive process (bash, ssh, python, gdb, docker, etc.) in a PTY.

    Args:
        command: Command to execute (defaults to platform shell: bash or powershell.exe).
        name: Optional friendly name for this session (e.g. 'router-ssh').
        cwd: Optional working directory.
        env: Optional environment variables dictionary.
        rows: Terminal rows (default: 40).
        cols: Terminal columns (default: 120).
    """
    sid = manager.spawn_pty(command=command, name=name, cwd=cwd, env=env, rows=rows, cols=cols)
    meta = manager.metadata.get(sid, {})
    cmd_name = meta.get("command", command or "default-shell")
    return {
        "success": True,
        "session_id": sid,
        "name": name or cmd_name,
        "command": cmd_name,
        "message": f"Spawned PTY session '{sid}' running: {cmd_name}",
    }


@mcp.tool()
def serial(
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
def list_ports() -> list[dict[str, Any]]:
    """Enumerate attached physical and virtual serial ports on the host."""
    return list_serial_ports()


@mcp.tool()
def exec_expect(
    command: str,
    prompts: list[str] | None = None,
    timeout: float = 8.0,
    session_id: str | None = None,
    interrupt_on_timeout: str | None = None,
) -> dict[str, Any]:
    """
    Execute a shell, REPL, or bootloader command and automatically wait for prompt to return.
    Output preserves original terminal stream (including command echo) as a causal anchor
    for AI analysis. ANSI escape codes are stripped for readability.

    Returns a structured result with 'success', 'output', 'timeout', 'process_exited',
    'exit_code', and 'elapsed_seconds' fields.

    IMPORTANT: For long-running commands (e.g. apt-get install, make, large file transfers),
    use send instead to dispatch the command, then poll with read_buffer periodically
    to check progress. Do NOT use exec_expect for commands that may take more than a few
    seconds, as it will report a timeout.

    Args:
        command: The command line to execute.
        prompts: Optional list of prompt patterns (defaults to standard shell and REPL prompts).
        timeout: Maximum seconds to wait for the prompt to return.
        session_id: Target session ID (defaults to currently active session).
    """
    try:
        _, sess = manager.get_session(session_id)
    except KeyError as e:
        return {"success": False, "error": str(e), "output": "", "timeout": False}
    return sess.exec_expect(command=command, prompts=prompts, timeout=timeout, interrupt_on_timeout=interrupt_on_timeout)


@mcp.tool()
def expect(
    patterns: list[str],
    command: str | None = None,
    timeout: float = 10.0,
    poll_cmd: str | None = None,
    poll_interval: float = 0.05,
    session_id: str | None = None,
    interrupt_on_timeout: str | None = None,
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
    try:
        _, sess = manager.get_session(session_id)
    except KeyError as e:
        return {"matched": False, "error": str(e), "output": ""}
    return sess.expect(
        patterns=patterns,
        timeout=timeout,
        command=command,
        poll_cmd=poll_cmd,
        poll_interval=poll_interval,
        interrupt_on_timeout=interrupt_on_timeout,
    )


@mcp.tool()
def send(
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
    try:
        sid, sess = manager.get_session(session_id)
    except KeyError as e:
        return f"Error: {e}"
    bytes_sent = sess.send(text=text, send_enter=send_enter)
    return f"Sent {bytes_sent} bytes to session '{sid}'."


@mcp.tool()
def read_buffer(
    clear: bool = False,
    session_id: str | None = None,
) -> str:
    """
    Read newly accumulated text from the stream buffer without blocking.

    Args:
        clear: If True, flushes the read buffer after fetching.
        session_id: Target session ID (defaults to currently active session).
    """
    try:
        _, sess = manager.get_session(session_id)
    except KeyError as e:
        return f"Error: {e}"
    buf = sess.read_buffer(clear=clear)
    return buf if buf else "(Buffer is currently empty)"


@mcp.tool()
def get_history(
    limit: int = 50,
    with_timestamps: bool = True,
    session_id: str | None = None,
) -> list[str]:
    """
    Retrieve recent chronological line history captured by the background daemon.

    By default, each line is prefixed with an accurate wall-clock timestamp
    [YYYY-MM-DD HH:MM:SS.mmm] captured at the transport reception level.
    If a line was split across packets with a pause of >= 50ms (e.g. driver pause,
    delayed response), the continuation line is prefixed with '↳ ' and tagged with
    its own timestamp for precise correlation against test framework logs.

    Args:
        limit: Number of recent lines to retrieve (default: 50).
        with_timestamps: If True (default), attaches wall-clock timestamps and continuation
            symbols on the fly. If False, returns raw clean text lines without timestamps.
        session_id: Target session ID (defaults to currently active session).
    """
    try:
        _, sess = manager.get_session(session_id)
    except KeyError as e:
        return [f"Error: {e}"]
    return sess.get_history(limit=limit, with_timestamps=with_timestamps)


@mcp.tool()
def list_sessions() -> list[dict[str, Any]]:
    """List all active PTY and Serial sessions with runtime health status."""
    return manager.list_sessions()


@mcp.tool()
def switch_session(session_id: str) -> str:
    """
    Switch the default active session.

    Args:
        session_id: Target session ID to make active.
    """
    if manager.switch_session(session_id):
        return f"Active session switched to '{session_id}'."
    return f"Error: Session '{session_id}' not found."


@mcp.tool()
def close_session(session_id: str | None = None) -> str:
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
def status(session_id: str | None = None) -> dict[str, Any]:
    """
    Check connection health, buffer statistics, and background daemon status.

    Args:
        session_id: Target session ID (defaults to active session).
    """
    try:
        sid, sess = manager.get_session(session_id)
    except KeyError as e:
        return {"error": str(e)}
    res = sess.status()
    res["session_id"] = sid
    return res


def main():
    """CLI Entrypoint for running expty-mcp server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
