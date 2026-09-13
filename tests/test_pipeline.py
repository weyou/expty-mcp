from termio_mcp.pipeline import decode_escape_sequences, strip_ansi


def test_decode_escape_sequences():
    assert decode_escape_sequences(r"\x03") == b"\x03"
    assert decode_escape_sequences(r"\r\n") == b"\r\n"
    assert decode_escape_sequences(r"hello\x20world") == b"hello world"
    assert decode_escape_sequences(r"中文测试\n") == "中文测试\n".encode()


def test_strip_ansi():
    # ANSI color codes
    colored = "\x1b[31mRed Text\x1b[0m and \x1b[1;32mBold Green\x1b[0m"
    cleaned, pending = strip_ansi(colored)
    assert cleaned == "Red Text and Bold Green"
    assert pending == ""

    # Terminal cursor/mode codes
    modes = "\x1b[?2004hprompt$ \x1b[?2004l"
    cleaned, pending = strip_ansi(modes)
    assert cleaned == "prompt$ "
    assert pending == ""

    # Window title (OSC)
    osc = "\x1b]0;my-window-title\x07bash-5.1$ "
    cleaned, pending = strip_ansi(osc)
    assert cleaned == "bash-5.1$ "
    assert pending == ""


def test_strip_ansi_cross_chunk_truncation():
    """Test that incomplete ANSI sequences at chunk boundaries are handled correctly."""
    # Simulate a color code split across two chunks
    chunk1 = "Hello \x1b["
    chunk2 = "31mWorld\x1b[0m"

    # First chunk: the incomplete ESC[ should be held as pending
    cleaned1, pending1 = strip_ansi(chunk1)
    assert "Hello" in cleaned1
    assert pending1 != ""  # Should hold the incomplete sequence

    # Second chunk: combine pending with new data to complete the sequence
    cleaned2, pending2 = strip_ansi(chunk2, pending=pending1)
    assert "World" in cleaned2
    assert "\x1b" not in cleaned2  # No raw escape chars in output
    assert pending2 == ""


def test_strip_ansi_with_pending():
    """Test the pending parameter works correctly for multi-chunk processing."""
    # Complete sequence in one chunk — no pending
    text = "\x1b[1;32mOK\x1b[0m done"
    cleaned, pending = strip_ansi(text)
    assert cleaned == "OK done"
    assert pending == ""
