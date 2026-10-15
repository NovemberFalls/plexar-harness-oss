"""Word. `read()` bytes -> Document, `write()` Document -> bytes."""

from ._read import read
from ._write import write

__all__ = ["read", "write"]
