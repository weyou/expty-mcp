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


# Regex to detect a potential incomplete ANSI escape sequence at end of chunk.
# Matches: ESC at the very end, or ESC followed by a partial CSI/OSC/charset sequence.
_ANSI_INCOMPLETE_RE = re.compile(
    r"\x1b"              # ESC character
    r"(?:"
    r"\[[\d;?]*[ -/]*"   # Partial CSI (missing final byte)
    r"|\][^\x07]*"       # Partial OSC (missing BEL or ST)
    r"|[\(\)]?"          # Partial charset designator
    r")?"
    r"$"                 # Must be at end of string
)


def fold_backspaces(text: str) -> str:
    """
    Simulate terminal cursor backspace (\\b / 0x08) movement and overwriting
    within lines.

    Handles cases where terminals/shells use cursor backspace to redraw or
    overwrite text (e.g. 'u\\buci' -> 'uci', '\\b i!\\bp' -> ' ip').
    """
    if "\b" not in text:
        return text

    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if "\b" not in line:
            cleaned_lines.append(line)
            continue
        buf: list[str] = []
        pos = 0
        for ch in line:
            if ch == "\b":
                pos = max(0, pos - 1)
            else:
                if pos < len(buf):
                    buf[pos] = ch
                else:
                    buf.append(ch)
                pos += 1
        cleaned_lines.append("".join(buf))
    return "\n".join(cleaned_lines)


def strip_ansi(text: str, pending: str = "") -> tuple[str, str]:
    """
    Strip ANSI escape codes (colors, cursor movements, title bars, bracketed paste)
    from text to provide a clean string for regex pattern matching and LLM presentation.

    Handles cross-chunk truncation: ``pending`` is a leftover fragment from the
    previous chunk that might form a complete escape sequence when combined with
    the start of this chunk.

    Returns:
        A tuple of (cleaned_text, new_pending) where new_pending holds any
        trailing bytes that look like an incomplete escape sequence.
    """
    text = pending + text

    # Check for an incomplete ANSI escape at the tail
    new_pending = ""
    # Only search in the last 20 chars for performance
    tail = text[-20:] if len(text) > 20 else text
    esc_pos = tail.rfind("\x1b")
    if esc_pos >= 0:
        # Found an ESC near the end; check if it's part of an incomplete sequence
        abs_pos = len(text) - len(tail) + esc_pos
        candidate = text[abs_pos:]
        # If the candidate doesn't match any complete ANSI pattern, hold it back
        test_cleaned = _ANSI_CSI_RE.sub("", candidate)
        test_cleaned = _ANSI_OSC_RE.sub("", test_cleaned)
        test_cleaned = _ANSI_CHARSET_RE.sub("", test_cleaned)
        test_cleaned = _ANSI_MISC_RE.sub("", test_cleaned)
        # If after stripping complete sequences there's still an ESC, it's incomplete
        if "\x1b" in test_cleaned:
            new_pending = candidate
            text = text[:abs_pos]

    text = _ANSI_OSC_RE.sub("", text)
    text = _ANSI_CSI_RE.sub("", text)
    text = _ANSI_CHARSET_RE.sub("", text)
    text = _ANSI_MISC_RE.sub("", text)
    # Normalize carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, new_pending
