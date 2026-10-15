"""Shared fixtures.

`started` is the session start every conversation key is derived from. It is
PINNED rather than `now()` so a test cannot race midnight — DEC-26 derives the
date segments from the session's start, and a suite that straddled 00:00 UTC
would write two prefixes and fail for a reason nobody could reproduce.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def started() -> datetime:
    return datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
