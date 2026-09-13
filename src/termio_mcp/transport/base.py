from abc import ABC, abstractmethod


class BaseTransport(ABC):
    """
    Abstract bidirectional I/O transport interface.
    Decouples underlying stream sources (PTY, Serial, etc.) from the Expect session engine.
    """

    @abstractmethod
    def read(self, max_bytes: int = 4096) -> bytes:
        """
        Read up to max_bytes from the transport non-blocking or with a minimal timeout.
        Returns b"" if no data is currently available.
        Raises EOFError if the stream reached end-of-file.
        """
        pass

    @abstractmethod
    def write(self, data: bytes) -> int:
        """
        Write raw bytes to the transport.
        Returns the number of bytes written.
        """
        pass

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the underlying process or device connection is alive."""
        pass

    @abstractmethod
    def get_exit_status(self) -> int | None:
        """Return process exit code or status if applicable, else None."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Cleanly terminate the process or close the device connection."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable description or identifier for this transport."""
        pass
