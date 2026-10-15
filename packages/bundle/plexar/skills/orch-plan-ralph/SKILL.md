---
name: orch-plan-ralph
description: "Plexar orchestration skill /orch-plan-ralph: /orch-plan, then stand the whole thing up in one push"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-plan-ralph.md"
  source_sha256: "6a261a21bf9336d81fb2fe3cf7e1a3f53dae1c792febbbda06cfafd440ff41b3"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-plan-ralph — /orch-plan, then stand the whole thing up in one push

**This is `/orch-plan` with the ralph flag set. It is a shim, not a second planning skill.**

> **Run `/orch-plan` in full — all of it, unabbreviated.** Interrogation with cross-framing,
> the approval questions, the nine-section `PLAN.md`, the decision log, milestones, QA
> obligations, every invariant. Nothing about planning is shortened because a loop is
> coming. A loop executing an un-interrogated backlog reaches the wrong destination faster
> and with less supervision.

Then do what is on this page, and only what is on this page. Two files that are "the same
except" diverge — planning guidance lives in `/orch-plan` and is never restated here.

**Use it for pass 1 of a new or mostly-empty repo.** Standing up a skeleton is where
per-node invocation costs the most and buys the least: the nodes are numerous, mostly
independent, mostly WORKHORSE/MUNDANE. Hand-driving forty of those is ceremony.

**Do not use it on a mature repo.** Where a change lands inside existing behavior and every
node carries real blast radius, use plain `/orch-plan` and drive the nodes deliberately.
A loop is a force multiplier in both directions.

---

## §1 · What the ralph flag adds to the plan

Two requirements the plan must satisfy before a loop may drive it:

- **Every node needs a genuinely deterministic `accept` command.** Hand-driven, a human
  notices a node that "passed" on a technicality. In a loop nobody is watching, so
  **accept *is* the supervision**. A node whose accept is `echo done` will be reported
  complete, and it will be wrong.
- **The backlog must be dependency-sorted, unblocking-first.** A loop that hits a
  dependency wall burns iterations discovering it.

## §2 · Ask which mode — explain, do not choose

Present both and ask. This is the human's call:

> **Attended** — each pass does a slice of the backlog, runs the gate, and stops, handing
> you the diff and the gate result before anything else happens. You approve, then run the
> next pass. You see every step before it compounds; a wrong turn costs one pass.
>
> **Unattended** — the loop runs itself until the backlog is done, a stop condition trips,
> or a ceiling is hit. You start it and walk away. Far faster and far cheaper in your
> attention; the cost is that a wrong turn in iteration 3 can be built on top of through
> iteration 30 before you see it.
>
> **Guidance: attended for the first two or three passes of any repo**, until you have seen
> what the loop actually does with your backlog — **then unattended for the long mechanical
> middle**, where the nodes are numerous and boring and the gate is real. Unattended from a
> cold start is how you get forty nodes of confidently wrong work.

Both modes emit the same harness; a flag selects behavior, and the human can switch at any
time. That is why both ship.

## §3 · The file set — exact, so "produces a ralph loop" is verifiable

```
ralph/
  PROMPT.md          invariant prompt, re-fed verbatim every iteration
  loop.ps1           Windows driver
  loop.sh            POSIX driver
  STATE.md           done / in progress / blocked   (agent-owned; the loop's memory)
  STOP               absent normally; create it to halt cleanly after the current pass
  logs/iter-NNN.md   per pass: nodes attempted, gate result, diff stat, cost
```

### §3a · The two drivers share one serialization contract

**Measured twice, 2026-08-06, and it cost a run each time.** `loop.ps1` and `loop.sh` read
and write the same files, and PowerShell's defaults produce files bash cannot read:

- `loop.ps1` written without a BOM is read as ANSI by PowerShell 5.1 — **seven parse
  errors, the Windows driver does not run at all**, and in one cell it had already
  corrupted `STATE.md` into mojibake.
- `loop.ps1` wrote `ralph/cost.json` **with** a UTF-8 BOM; `loop.sh` could not parse it,
  the budget flag came through empty, the CLI rejected it, and **two passes died in one
  second each and tripped the no-progress halt.** The loop halted cleanly and wrote a
  reason — it just wrote the *wrong* reason, which is worse than halting loudly.

**Rules, because "be careful with encodings" is not a rule:**

- Every file both drivers touch — `STATE.md`, `cost.txt`/`cost.json`, the iteration logs —
  is **UTF-8 without a BOM**. In PowerShell that means `[IO.File]::WriteAllText` with
  `UTF8Encoding($false)`, not `Out-File` or `Set-Content`.
- **`loop.ps1` itself carries a BOM**, or is ASCII-only. That is the opposite of the rule
  above and both are needed: 5.1 needs the BOM to read the *script*; bash needs its absence
  to read the *data*.
- The harness's self-test must **round-trip one file through both drivers** before the first
  real pass. Both defects above would have been caught by one such check.

**`PROMPT.md` is invariant** — the same text every iteration. That is the whole technique.
It does not accumulate history, because the state that matters lives in `STATE.md` and in
the repo. A prompt that grows each pass is a different technique and it degrades.

Its content, roughly:

> Read `PLAN.md` and `ralph/STATE.md`. Pick the highest-priority unblocked, unfinished
> nodes. Run `/orch-code-anth` on them. Run each node's accept command. Update `STATE.md`
> with what landed, what failed and why, and what is now unblocked. Commit each node as its
> own candidate commit. If a milestone completed, write the alert into `STATE.md`. If you
> are blocked on something only a human can answer, write it under BLOCKED and stop.

## §4 · Stop conditions — all seven, whichever fires first

1. **Done** — no unblocked, unfinished nodes remain.
2. **`ralph/STOP` exists** — the human's clean brake. Checked *between* passes, so nothing
   is interrupted mid-edit.
3. **Max iterations** — hard cap, default 40.
4. **Cost ceiling** — set by the human up front. Checked every iteration, non-negotiable.
5. **No-progress** — two consecutive iterations with no node completed and no new commit.
   The important one: **a stuck loop looks exactly like a working loop from outside**, and
   without this check it burns the entire ceiling proving it.
6. **Gate red at iteration start** — the tree was left broken. Stop; never build on it.
7. **BLOCKED in `STATE.md`** — something only a human can answer.

Every halt writes its reason to `STATE.md` and the final log. **A loop that stops without
saying why is indistinguishable from one that finished.**

## §5 · What the loop must never do

- **Never touch a §6 destructive surface unattended.** Auth, money, concurrency,
  migrations, production data: present the node as a plan with rollback and wait for a
  human. **Skip it and continue with the rest of the backlog** rather than halting the whole
  stand-up on one node. An autonomous loop is where the interlock matters most and where it
  is most tempting to weaken it.
- **Never push, merge, deploy, or release.** Local candidate commits only.
- **Never mark a QA item passed.** Milestone completion writes the alert to `STATE.md`; QA
  is its own phase with its own authority rules. A loop that grades its own work is the
  failure mode this whole toolchain exists to prevent.
- **Never rewrite a decision** in `PLAN.md` §3. It may append discovered nodes to the
  backlog; changing a logged decision needs a human.

## §6 · Reading the result

1. `ralph/STATE.md` — what it thinks it did, and why it stopped.
2. `git log --oneline` — what it actually did. **These two disagreeing is the finding.**
3. The last two or three `ralph/logs/iter-*.md` — where it was when it stopped.
4. Then `/orch-qa` for completed milestones, and `/orch-clean` if the run did renames,
   signature migrations, or removals.

**Expect to re-plan after pass 1.** A stand-up run's real output is a working skeleton *and
a much better-informed backlog* — the nodes that were harder than they looked, the
assumptions that broke, the infrastructure marked UNKNOWN that is now known. `/orch-plan`
merges on re-run rather than clobbering, so feeding that back is cheap and the second pass
is far sharper than the first could have been.

## Invariants

- All `/orch-plan` invariants hold, unabbreviated. This file adds; it never replaces.
- No planning guidance is restated here. One engine, one flag.
- Every node has a real deterministic accept command. In a loop, accept *is* supervision.
- Both modes are offered and the difference is explained; the human chooses.
- `PROMPT.md` is invariant across iterations. State lives in `STATE.md` and the repo.
- All seven stop conditions are implemented, including no-progress and cost ceiling.
  Every halt records its reason.
- Destructive surfaces, publication, and QA promotion are never done by the loop, in any
  mode.
