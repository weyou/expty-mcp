# termio-mcp

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**`termio-mcp`** is a high-performance **Model Context Protocol (MCP)** server that equips AI assistants (Claude Code, Cursor, Antigravity, VS Code) with persistent, zero-loss **Interactive PTY Process and Serial Communication** capabilities.

Engineered specifically for **persistent SSH sessions, remote server administration, local shells, REPLs, container debugging, and hardware serial ports (UART/U-Boot)**, featuring a dedicated **Atomic Expect Engine**, continuous background ingestion daemon, and automatic ANSI/echo cleaning pipelines.

---

## ✨ Key Features

- ⚡ **Zero-Loss Background Daemon**: Dedicated reader thread continuously ingests bytes into memory in real time—eliminating dropped output during LLM reasoning pauses.
- 🔌 **Unified PTY & Serial Transports**: Seamlessly spawn local processes (`bash`, `python`, `gdb`), SSH sessions (`ssh user@router`), or connect to physical UART devices (`/dev/ttyUSB0`).
- 🎯 **Atomic Expect Engine (`termio_expect`)**: Match regex or substring prompt patterns atomically (`['password:', '# ', '>>>']`) with buffer slicing and retention.
- 🚀 **Prompt-Aware Execution (`termio_exec_expect`)**: Send commands and automatically wait for prompt to return in a single tool call, stripping ANSI color codes and command echo.
- 🤹 **Multi-Session Management**: Concurrently manage multiple terminal sessions with smart active-session auto-resolution.
- ⏱️ **Fast Process Exit Detection**: Instantly detects when a child process or SSH connection terminates, returning exit codes immediately without waiting for timeouts.
- 🔄 **Periodic Injection (`poll_cmd`)**: Inject keepalive characters or autoboot interrupt keys (e.g. spaces for U-Boot) at high frequency during expect wait windows.

---

## 🛠️ Available MCP Tools

| Tool | Description |
| :--- | :--- |
| **`termio_spawn`** | Spawn a new interactive process (`bash`, `ssh user@host`, `python`, `gdb`, etc.) in a PTY. |
| **`termio_serial`** | Connect to a physical or virtual serial port (`/dev/ttyUSB0`, `COM3`). |
| **`termio_exec_expect`** | Execute command and wait for prompt to return, extracting clean output without echo. |
| **`termio_expect`** | Atomically send a command and wait for regex patterns (ideal for SSH login / prompts). |
| **`termio_send`** | Send raw keys or escape sequences (e.g. `\x03` for Ctrl+C, `\x1b` for Escape, Enter). |
| **`termio_read_buffer`** | Non-blocking read of newly accumulated stream buffer. |
| **`termio_get_history`** | Fetch recent line history captured by the background daemon. |
| **`termio_list_sessions`**| List all active PTY and Serial sessions with runtime health status. |
| **`termio_switch_session`**| Switch the default active session. |
| **`termio_close_session`** | Terminate and clean up an active session. |
| **`termio_list_ports`** | Enumerate connected physical and virtual serial ports on the host. |
| **`termio_status`** | Query runtime diagnostics, buffer usage, and transport health. |

---

## 💡 Practical Examples

### 1. Persistent SSH Session (No repeated logins)

```json
// Step 1: Spawn SSH connection
// Tool: termio_spawn
{
  "command": "ssh root@192.168.1.1",
  "name": "openwrt-router"
}

// Step 2: Handle password prompt with Expect
// Tool: termio_expect
{
  "patterns": ["password:", "# "],
  "command": "admin",
  "timeout": 10.0
}

// Step 3: Run interactive commands effortlessly
// Tool: termio_exec_expect
{
  "command": "cat /etc/config/network"
}
```

### 2. Interactive Python REPL / Debugger

```json
// Tool: termio_spawn
{
  "command": "python3",
  "name": "python-repl"
}

// Tool: termio_exec_expect
{
  "command": "import math; math.factorial(10)"
}
```

### 3. Hardware UART Bootloader Interception

```json
// Step 1: Open serial port
// Tool: termio_serial
{
  "port": "/dev/ttyUSB0",
  "baudrate": 115200
}

// Step 2: Interrupt autoboot with high-frequency space injection
// Tool: termio_expect
{
  "patterns": ["IPQ807x#", "U-Boot#"],
  "poll_cmd": " ",
  "poll_interval": 0.05,
  "timeout": 15.0
}
```

---

## 📦 Installation & Configuration

### Local Installation

```bash
cd ~/dev/termio-mcp
pip install -e .
```

### Configuration

#### 1. Claude Desktop
Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "termio": {
      "command": "python3",
      "args": ["-m", "termio_mcp"]
    }
  }
}
```

#### 2. Antigravity / Google AI Assistant
Add to `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "termio": {
      "command": "python3",
      "args": ["-m", "termio_mcp"]
    }
  }
}
```

#### 3. Cursor IDE
Add to `.cursor/mcp.json` or Cursor Global Settings:

```json
{
  "mcpServers": {
    "termio": {
      "command": "python3",
      "args": ["-m", "termio_mcp"]
    }
  }
}
```

---

## 🧪 Testing

```bash
cd ~/dev/termio-mcp
pytest -v
ruff check .
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
