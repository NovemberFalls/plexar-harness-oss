# plexar-harness CLI — QA Passed Ledger

Append-only. A pass is a fact with a date attached, not a checkbox. Rows are never edited or removed; a later failure goes in [`QA_PLAN.md`](QA_PLAN.md).

| ID | Test | Class | Auth | Passed | By | Build | Exercises | Evidence |
|----|------|-------|------|--------|----|-------|-----------|----------|
| A.1 | live end-to-end gate | MACHINE | AUTO | 2026-09-23 | orch-qa (harness session) | 4eb79f03ae | `packages/bundle/plexar/cli/` `packages/acp/acp/src/session.ts` | `python packages/bundle/plexar/cli/tests/live_gate.py` → exit 0, 24/24 PASS |
| A.2 | terminal UI redraw and markers | MACHINE | AUTO | 2026-09-23 | orch-qa (harness session) | 4eb79f03ae | `packages/bundle/plexar/cli/tui/composer.mjs` `packages/bundle/plexar/cli/tui/select.mjs` `packages/bundle/plexar/cli/tui/term.mjs` | `node packages/bundle/plexar/cli/tests/tui.test.mjs` → exit 0, 7/7 PASS; same test on `ba8f30776c` → exit 1, 4 FAIL |
| B.1 | header and mark | HUMAN | OWNER | 2026-09-23 | owner | ba8f30776c | `packages/bundle/plexar/cli/logo.mjs` (module) | owner verdict "that was sexy", MINGW64 terminal |
