"""Fail when upstream's ACP surface drifts from the Studio contract (v2).

Run after every `git merge upstream/master` (and in CI):

    python packages/bundle/plexar/studio/check_api_drift.py

Compares three things that must agree:
  1. upstream `packages/acp/acp` (handlers, config option ids, permission option ids,
     pinned `@agentclientprotocol/sdk` version) — the source of truth,
  2. `plexar_harness_client.py` (REQUESTS, CONFIG_OPTIONS, the permission ids it answers),
  3. `docs/plexar/07-studio-api-contract.md` (the pinned fingerprint line, every method named).
Exit 0 = in sync. Exit 1 = drift; the output names what moved.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ACP = ROOT / "packages/acp/acp"
CONTRACT = ROOT / "docs/plexar/07-studio-api-contract.md"
sys.path.insert(0, str(Path(__file__).parent))
import plexar_harness_client as client  # noqa: E402

# ACP handler name -> wire method the client sends for it.
HANDLER_TO_METHOD = {
    "initialize": "initialize", "newSession": "session/new", "listSessions": "session/list",
    "resumeSession": "session/resume", "prompt": "session/prompt",
    "setSessionConfigOption": "session/set_config_option", "closeSession": "session/close",
}
PERMISSION_IDS = ("allow-once", "reject-once")


def surface() -> dict:
    index = (ACP / "src/index.ts").read_text(encoding="utf8")
    model = (ACP / "src/model-control.ts").read_text(encoding="utf8")
    pkg = json.loads((ACP / "package.json").read_text(encoding="utf8"))
    return {
        "handlers": sorted(set(re.findall(r"^\s{4}async (\w+)\(", index, re.M))),
        "config_ids": sorted(re.findall(r"const \w+_CONFIG_ID = '([\w-]+)'", model)),
        "permission_ids": sorted(set(re.findall(r"optionId: '([\w-]+)'", index))),
        "acp_sdk": pkg.get("dependencies", {}).get("@agentclientprotocol/sdk"),
    }


def fingerprint(s: dict) -> str:
    return hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]


def main() -> int:
    s = surface()
    fail = []
    expected_handlers = sorted(HANDLER_TO_METHOD)
    if s["handlers"] != expected_handlers:
        fail.append(f"ACP handlers moved: upstream {s['handlers']} != pinned {expected_handlers}")
    methods = tuple(HANDLER_TO_METHOD[h] for h in HANDLER_TO_METHOD)
    if set(client.REQUESTS) != set(methods):
        fail.append(f"client REQUESTS {client.REQUESTS} != pinned {methods}")
    if tuple(sorted(client.CONFIG_OPTIONS)) != tuple(s["config_ids"]):
        fail.append(f"config options: upstream {s['config_ids']} != client {client.CONFIG_OPTIONS}")
    if tuple(s["permission_ids"]) != tuple(sorted(PERMISSION_IDS)):
        fail.append(f"permission option ids: upstream {s['permission_ids']} != pinned {PERMISSION_IDS}")
    src = Path(client.__file__).read_text(encoding="utf8")
    for pid in PERMISSION_IDS:
        if f'"{pid}"' not in src:
            fail.append(f"client never answers with {pid!r}")
    fp = fingerprint(s)
    doc = CONTRACT.read_text(encoding="utf8") if CONTRACT.exists() else ""
    pinned = re.search(r"Wire fingerprint: `([0-9a-f]{16})`", doc)
    if not pinned:
        fail.append("contract doc has no 'Wire fingerprint: `...`' line")
    elif pinned.group(1) != fp:
        fail.append(f"wire fingerprint moved: contract {pinned.group(1)} != upstream {fp} ({s}); "
                    "re-read packages/acp/acp, update the client + contract, then re-pin")
    names = client.REQUESTS + client.CLIENT_NOTIFICATIONS + client.SERVER_NOTIFICATIONS + client.SERVER_REQUESTS
    for m in names:
        if f"`{m}`" not in doc:
            fail.append(f"contract doc never names `{m}`")
    if fail:
        print(f"API DRIFT (contract v{client.CONTRACT_VERSION}):")
        for f in fail:
            print("  -", f)
        return 1
    print(f"in sync: contract v{client.CONTRACT_VERSION}, {len(client.REQUESTS)} requests, ACP sdk {s['acp_sdk']}, fingerprint {fp}")
    return 0


if __name__ == "__main__":
    if "--print-fingerprint" in sys.argv:
        print(fingerprint(surface()))
        sys.exit(0)
    sys.exit(main())
