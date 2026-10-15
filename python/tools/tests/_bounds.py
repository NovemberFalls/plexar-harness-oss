"""The instrument every hostile arm in T84's gate shares.

══ A DEADLINE-ONLY ARM MEASURES THE WRONG THING ═══════════════════════════
An arm that returns in four seconds while resident at three gigabytes has not
shown that a bound holds — the 400x-`/Contents` file measured **9.1s and
3,366 MB** before T84 and the memory was the part that would have taken the box
down. So every hostile arm here asserts a wall-clock ceiling **and** a
peak-allocation ceiling.

══ AND THE TWO ARE MEASURED IN SEPARATE PASSES, WHICH IS T84's OWN INSTRUMENT
══ FAULT WRITTEN DOWN ═════════════════════════════════════════════════════
`tracemalloc` traces every allocation, so it inflated that row's first timings
by up to **17x — 6.4s where the truth was 0.40s.** A number 17x too large is not
conservative, it is a different diagnosis: it made a linear cost look like a
runaway and would have bought a bound tight enough to truncate a real document.
**`elapsed()` never starts the tracer and `peak_mib()` never reports a time.**

`tracemalloc` rather than RSS, deliberately. RSS is the number the audit cares
about, and it needs `psutil` — which is installed on this machine and is not a
dependency of this repo, so an arm built on it would either add one or carry a
`pytest.skip` branch, and a skip that nobody notices is a self-inflicted green
(T10). Every quantity that was unbounded here is a Python object — a
`bytearray` of page content, a list of table rows, a dict of CMap entries, a
list of grid pointers — and those are exactly what the tracer counts. Where the
honest ceiling is a COUNT rather than a size (operators spent, `run()`
invocations, grid cells materialised) the arm asserts the count instead, because
a count is the same number on a faster machine.

══ THE CEILINGS ARE NOT PICKED TO JUST-PASS ═══════════════════════════════
Every ceiling in these files is at least ~5x the measurement taken on this
machine, and the docstring of each arm carries the measured number next to the
ceiling so the next reader can tell a flake from a regression. Where a ceiling
CANNOT separate the fix from the defect — the predictor refusal is 0.3ms against
a pre-fix 551ms, and no sane deadline sits between them — the arm says so and
the discriminator is the refusal itself.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import Any, Callable


def elapsed(work: Callable[[], Any]) -> tuple[float, BaseException | None, Any]:
    """Run `work` once, untraced, and report `(seconds, raised, result)`.

    The exception is RETURNED rather than raised so an arm can assert the
    deadline and the refusal in either order — a refusal that arrives after
    forty seconds is still a denial of service.
    """
    started = time.perf_counter()
    try:
        result = work()
    except BaseException as caught:  # noqa: BLE001 — a MemoryError is a finding
        return time.perf_counter() - started, caught, None
    return time.perf_counter() - started, None, result


def peak_mib(work: Callable[[], Any]) -> float:
    """Peak traced allocation for one run of `work`, in MiB. **Second pass.**

    Never call this in the same pass as `elapsed`; see the module docstring.
    A raise is swallowed because most of these bounds REFUSE, and the memory
    spent on the way to the refusal is exactly what is being measured.
    """
    tracemalloc.start()
    try:
        try:
            work()
        except BaseException:  # noqa: BLE001
            pass
        return tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    finally:
        tracemalloc.stop()
