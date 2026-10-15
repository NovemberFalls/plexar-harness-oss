"""Host-free tools shared with Chat over MCP (chat-DEC-397).

Exposes exactly five tools: `read_file`, `find_in_file`, `query_sheet`,
`convert_document`, `create_document`. Each receives only bytes/text and arguments; none of
them import a user, store, bucket, R2, conversation, sub, App, or
chat.api/chat.store concept. Ownership resolution stays in the consumer.
"""

from ._contract import (
    MAX_RESULT_CHARS,
    MAX_TOOL_ROUNDS,
    ToolBox,
    ToolCall,
    ToolResult,
)
from ._convert import CONVERT_DOCUMENT
from ._document import CREATE_DOCUMENT
from ._findfile import CONTEXT as FIND_CONTEXT
from ._findfile import FIND_IN_FILE
from ._findfile import MAX_HITS as FIND_MAX_HITS
from ._querysheet import MAX_PAIRS as SHEET_MAX_PAIRS
from ._querysheet import MAX_ROWS as SHEET_MAX_ROWS
from ._querysheet import QUERY_SHEET
from ._readfile import MAX_WINDOW as READ_WINDOW
from ._readfile import READ_BUDGET_PER_TURN
from ._readfile import READ_FILE
from ._registry import Handler, Registry, Tool

__all__ = [
    "MAX_RESULT_CHARS",
    "MAX_TOOL_ROUNDS",
    "FIND_CONTEXT",
    "FIND_MAX_HITS",
    "READ_BUDGET_PER_TURN",
    "SHEET_MAX_PAIRS",
    "SHEET_MAX_ROWS",
    "READ_WINDOW",
    "Handler",
    "Registry",
    "Tool",
    "ToolBox",
    "ToolCall",
    "ToolResult",
    "READ_FILE",
    "FIND_IN_FILE",
    "QUERY_SHEET",
    "CONVERT_DOCUMENT",
    "CREATE_DOCUMENT",
]
