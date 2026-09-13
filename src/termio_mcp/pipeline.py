import re

# Escape sequence pattern: \xNN hex, or \n \r \t \\ \0
_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})|\\([nrt\\0])")
_ESCAPE_CHARS = {"n": 0x0A, "r": 0x0D, "t": 0x09, "\\": 0x5C, "0": 0x00}

# ANSI escape sequence patterns
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(\x07|\x1b\\)")
_ANSI_CHARSET_RE = re.compile(r"\x1b[\(\)][A-Z0-9]")
_ANSI_MISC_RE = re.compile(r"\x1b[=>M78]")


def decode_escape_sequences(text: str) -> bytes:
    """
    Decode recognized escape sequences (\\xNN, \\n, \\r, \\t, \\\\, \\0) into raw bytes.
    Preserves multibyte UTF-8 characters without blanket unicode_escape corruption.
    """
    result = bytearray()
    pos = 0
    for m in _ESCAPE_RE.finditer(text):
        if m.start() > pos:
            result.extend(text[pos : m.start()].encode("utf-8"))
        hex_val, char_key = m.groups()
        if hex_val is not None:
            result.append(int(hex_val, 16))
        else:
            result.append(_ESCAPE_CHARS[char_key])
        pos = m.end()
    if pos < len(text):
        result.extend(text[pos:].encode("utf-8"))
    return bytes(result)


def strip_ansi(text: str) -> str:
    """
    Strip ANSI escape codes (colors, cursor movements, title bars, bracketed paste)
    from text to provide a clean string for regex pattern matching and LLM presentation.
    """
    text = _ANSI_OSC_RE.sub("", text)
    text = _ANSI_CSI_RE.sub("", text)
    text = _ANSI_CHARSET_RE.sub("", text)
    text = _ANSI_MISC_RE.sub("", text)
    # Normalize carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def strip_command_echo(output: str, command: str) -> str:
    """
    Remove initial command echo commonly produced by TTY/PTY line discipline.
    """
    cmd_clean = command.strip()
    if not cmd_clean:
        return output

    lines = output.splitlines(keepends=True)
    if not lines:
        return output

    # Check if the first line contains the executed command
    first_line = lines[0].strip()
    if first_line == cmd_clean or first_line.endswith(cmd_clean):
        return "".join(lines[1:]).lstrip("\r\n")

    return output
