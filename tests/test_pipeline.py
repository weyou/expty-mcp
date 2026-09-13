from termio_mcp.pipeline import decode_escape_sequences, strip_ansi, strip_command_echo


def test_decode_escape_sequences():
    assert decode_escape_sequences(r"\x03") == b"\x03"
    assert decode_escape_sequences(r"\r\n") == b"\r\n"
    assert decode_escape_sequences(r"hello\x20world") == b"hello world"
    assert decode_escape_sequences(r"中文测试\n") == "中文测试\n".encode()


def test_strip_ansi():
    # ANSI color codes
    colored = "\x1b[31mRed Text\x1b[0m and \x1b[1;32mBold Green\x1b[0m"
    assert strip_ansi(colored) == "Red Text and Bold Green"

    # Terminal cursor/mode codes
    modes = "\x1b[?2004hprompt$ \x1b[?2004l"
    assert strip_ansi(modes) == "prompt$ "

    # Window title (OSC)
    osc = "\x1b]0;my-window-title\x07bash-5.1$ "
    assert strip_ansi(osc) == "bash-5.1$ "


def test_strip_command_echo():
    cmd = "uname -a"
    raw_output = "uname -a\r\nLinux router 5.15.0 #1 SMP\r\n"
    cleaned = strip_command_echo(raw_output, cmd)
    assert cleaned.strip() == "Linux router 5.15.0 #1 SMP"

    # When no echo is present
    no_echo = "Linux router 5.15.0\r\n"
    assert strip_command_echo(no_echo, cmd) == no_echo
