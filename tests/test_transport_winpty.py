from unittest.mock import MagicMock, patch

import pytest

from termio_mcp.transport.base import BaseTransport
from termio_mcp.transport.factory import get_default_shell


def test_get_default_shell():
    shell = get_default_shell()
    assert isinstance(shell, str)
    assert len(shell) > 0


def test_winpty_transport_mocked():
    # Test WinPtyTransport initialization and interface conformance using a mock winpty
    mock_proc = MagicMock()
    mock_proc.isalive.return_value = True
    mock_proc.pid = 12345
    mock_proc.read.return_value = "Windows PowerShell\r\nPS C:\\> "
    mock_proc.exitstatus = None

    mock_winpty = MagicMock()
    mock_winpty.PtyProcess.spawn.return_value = mock_proc

    with patch("termio_mcp.transport.winpty.WinPtyProcess", mock_winpty.PtyProcess):
        with patch("termio_mcp.transport.winpty._WINPTY_AVAILABLE", True):
            from termio_mcp.transport.winpty import WinPtyTransport

            transport = WinPtyTransport(command="powershell.exe", rows=30, cols=100)
            assert isinstance(transport, BaseTransport)
            assert transport.is_alive() is True
            assert "ConPTY[powershell.exe]" in transport.display_name

            # Test read
            data = transport.read(1024)
            assert b"Windows PowerShell" in data

            # Test write
            written = transport.write(b"dir\r\n")
            assert written == 5
            mock_proc.write.assert_called_with("dir\r\n")

            # Test resize
            transport.resize(50, 150)
            mock_proc.setwinsize.assert_called_with(50, 150)

            # Test close
            transport.close()
            assert transport.is_alive() is False


def test_winpty_transport_queue_empty_and_eof():
    mock_proc = MagicMock()
    mock_proc.isalive.return_value = True
    mock_proc.pid = 9999
    # Simulate empty read first, then EOF
    mock_proc.read.return_value = ""

    mock_winpty = MagicMock()
    mock_winpty.PtyProcess.spawn.return_value = mock_proc

    with patch("termio_mcp.transport.winpty.WinPtyProcess", mock_winpty.PtyProcess):
        with patch("termio_mcp.transport.winpty._WINPTY_AVAILABLE", True):
            from termio_mcp.transport.winpty import WinPtyTransport

            transport = WinPtyTransport(command="cmd.exe")
            # When queue is empty and process is alive, returns empty bytes
            assert transport.read(1024, timeout=0.01) == b""

            # When process terminates
            mock_proc.isalive.return_value = False
            with pytest.raises(EOFError):
                transport.read(1024, timeout=0.01)

            transport.close()


def test_winpty_missing_dependency():
    with patch("termio_mcp.transport.winpty._WINPTY_AVAILABLE", False):
        from termio_mcp.transport.winpty import WinPtyTransport

        with pytest.raises(RuntimeError, match="pywinpty is not installed"):
            WinPtyTransport(command="cmd.exe")
