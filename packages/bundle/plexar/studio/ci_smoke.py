"""Rigless CI smoke for the Studio client: fake rig + real harness through `plexar-harness acp`.

Usage: python ci_smoke.py [workspace]   (exit 0 = every check passed; needs `plexar-harness` on PATH)

Checks: a prompt answers `PLEXAR_OK` through the fake rig, and the launcher's pre-ACP failures reach the
client as distinct `HarnessError.reason` values: key_missing (11), key_rejected (13), rig_unreachable (14).
"""
from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plexar_harness_client import HarnessError, HarnessRuntime, text_of  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plexar-ci-"))
    port = free_port()
    rig = subprocess.Popen([sys.executable, str(HERE / "fake_rig.py"), "--port", str(port)])
    time.sleep(1)
    env = {"PLEXAR_RIG_URL": f"http://127.0.0.1:{port}", "PLEXAR_HARNESS_KEY": "ci"}
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
        if not ok:
            fails.append(name)

    try:
        runtime = HarnessRuntime(workspace, env=env)
        check("launcher on PATH", runtime.command()[-1] == "acp", str(runtime.command()))
        with runtime:
            sid = runtime.new_session()["sessionId"]
            result = runtime.prompt(sid, "Say anything.")
            check("prompt answers through the fake rig", text_of(runtime.drain(sid)) == "PLEXAR_OK", str(result))
        for reason, extra in [("key_missing", {"PLEXAR_HARNESS_KEY": ""}),
                              ("key_rejected", {"PLEXAR_HARNESS_KEY": "rejected"}),
                              ("rig_unreachable", {"PLEXAR_RIG_URL": f"http://127.0.0.1:{free_port()}"})]:
            try:
                HarnessRuntime(workspace, env={**env, **extra}).start(timeout=60)
                check(reason, False, "started instead of failing")
            except HarnessError as error:
                check(reason, error.reason == reason, f"exit={error.exit_code} reason={error.reason}")
    finally:
        rig.terminate()
    print("SMOKE", "FAIL " + ",".join(fails) if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
