"""PDF. **Read and write since T78.**

The header here said *"write only — reading one is a font and encoding problem
with no structure to recover, and it deserves its own row rather than a half of
one."* It got its row. Both halves of that sentence were true and neither was a
reason to leave a format this product can WRITE unreadable: `_read` recovers the
text and the pictures out of the geometry and says plainly what it cannot
recover. See its own header for the list.
"""

from ._read import NoTextInPDF, PDFRefused, read
from ._write import write

__all__ = ["NoTextInPDF", "PDFRefused", "read", "write"]
