---
name: orch-code-local
description: "Plexar orchestration skill /orch-code-local: v5.0.1-RIG (/orch-code-anth's flow · the rig does every change · the orchestrator plans once and reviews)"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-code-local.md"
  source_sha256: "e228ba030750ea9b9a28bf982e5847bdfdb19e8c4971a4e89e4d17a083212cb2"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-code-local — v5.0.1-RIG (/orch-code-anth's flow · the rig does every change · the orchestrator plans once and reviews)

> ### §10 FIRES AT FIVE POINTS IN THE FLOW BELOW — NOT AT THE END WHERE IT IS WRITTEN
>
> `run_start` at **inventory** · `plan` at **plan freeze** · `dispatch` at **every spawn AND
> every SOLO node** · `outcome` when **each report lands** · `run` at **landing**.
>
> §10 is mandatory and it is the last section in this file purely for readability. **A run
> that reaches the inventory and writes nothing has already lost data that cannot be
> recovered afterwards** — the 2026-09-21 PDF-builder run did exactly that, because §1 said
> nothing about logging and §10 sat 420 lines later. **Read §10 before acting on §1.**


STATUS: **PROPOSED bench arm, NOT LIVE.** Unmeasured. Same graduation bar as any arm: arena
k=25 against `/orch-code-anth` and `/orch-code-anth-local` before anything relies on it.

**What this is (2026-09-17).** `/orch-code-anth` v5.0.1 — same inventory, gate, plan, grouping,
mandate, landing, gate script, destructive interlock, reconciliation — with ONE change of
executor and ONE added loop. Rig-specific rules are marked **[RIG]**; unmarked rules are
v5.0.1.

**[RIG] The goal: protect frontier tokens.** Three parts only — the ORCHESTRATOR (the one
API seat), the RIG, and the rig's MODELS. The orchestrator does the investigative work ONCE:
reads the spec, finds the sites, draws the dependency graph, decides what changes, writes the
plan, the work orders and the gate. Then it hands off ALL execution — mechanical and reasoned,
CRITICAL included — to rig workers. A worker says DONE; the orchestrator runs the gate,
reviews, and APPROVES or REJECTS with exactly what to fix; the loop runs until approved. The
orchestrator steps in to write code only when a worker has repeatedly failed (§4.8). There are
no API workers and no haiku/sonnet/opus fallback.

**Why this costs fewer frontier tokens than `/orch-code-anth`:** the orchestrator's output is
plans, work orders, gate scripts and short verdicts — never implementation and never
per-site SEARCH/REPLACE text for large sweeps. Wall-clock is traded away on purpose.

Objective order: **correctness → frontier-token protection → wall-clock → raw dollars.**
Local $ are reported as 0.

**Self-containment rule.** Everything this skill requires is written HERE. A rule you believe
lives in another document is a defect in this file — report it, never infer it.

**Orchestrator effort.** `opus / low` DEFAULT (or `fable`): the gate and the review loop are
watching, so the seat executes a plan rather than deliberating. `opus / high` when the plan
itself is the hard part (unfamiliar codebase, unpinned contracts). Never `medium`/`xhigh`.

---

## §0 · Change-kind split (after §1, before SOLO/SWARM)

For each node, from the investigation you already did:

- **MECHANICAL** — expressible as before/after text swaps against existing files (renames,
  API/logging migrations, signature threading, config edits). The work order gives the RULE,
  2–3 verbatim before → after examples, the exclusions, and the SITE LIST you already found
  (`file:line`, from your grep — you do not read each site to write its replacement). The rig
  worker produces SEARCH/REPLACE blocks; the deterministic applier (§4.9) lands them.
  - **Tiny exception:** ≤ ~5 sites whose text is already in your context → emit the blocks
    yourself; a work order would cost more. Never read files just to do this.
- **REASONED** — new files, structural rewrites, algorithms, anything needing inference. A rig
  worker implements it from a work order (§4.5).

Print `CHANGE-KIND: MECHANICAL n=<nodes> sites=<n> | REASONED n=<nodes> | orch-blocks=<sites>`.

MIXED is normal: build and approve the CRITICAL contract first, then fan out the mechanical
call-site migrations against the landed file.

## §1 · Inventory (mandatory, before choosing anything)
**→ FIRST, before anything below: write the `run_start` row (§10).**


**[RIG] STEP ZERO — your literal FIRST tool call:**

```
sh -c 'cat "$LOCAL_LANES_PROFILE" 2>/dev/null || cat ~/.claude/local-lanes.json 2>/dev/null || cat ./bench/local_lane/local-lanes.json 2>/dev/null || echo PROFILE-MISSING'
```

Then for each lane: `curl -s -H "Authorization: Bearer $<auth_env>" <endpoint>/v1/models` — a
lane is USABLE only if its `model` is listed serving. Print `RIG: <lane-id>=<model> serving|down, ...`.

- `PROFILE-MISSING`, a STALE profile (LM Studio, `:1234`/`:1235`, desktop `127.0.0.1`,
  `max_concurrent: 1`), or zero usable lanes → **STOP and tell the human.** This skill has no
  API fallback; running on the API is `/orch-code-anth`, the human's call.
- The profile's per-lane `never: ["CRITICAL", ...]` belongs to `/orch-code-anth-local`. This
  skill ignores it for CRITICAL and honours it for DESTRUCTIVE (§6).

Read the task and the spec/source. COUNT the real work — this is the ONE investigation pass;
do it thoroughly so nothing needs re-investigating later:

- **sites** — individual edit/creation points (grep the call sites; list the stubs)
- **files** — files to create or modify
- **read volume** — bytes that must be read (`wc -c`, ÷4 ≈ tokens)
- **nodes** — discrete deliverables, labeled by RISK:
  - **CRITICAL** — shared contracts others import · auth/security · money math · concurrency ·
    migrations · anything DESTRUCTIVE (§6)
  - **WORKHORSE** — contained implementation against a clear spec · trap-dense edits
  - **MUNDANE** — mechanical, fully specified, judgment-light

## §2 · Scale gate (computed — print, then obey)

`GATE: SOLO|SWARM — sites=<n> files=<n> read≈<n>K nodes=<n> mix=<C/W/M>`

**SWARM** if ANY: sites ≥ 25 · files ≥ 12 · nodes ≥ 12 AND ≥ 40% MUNDANE+WORKHORSE ·
read ≥ 150K tokens or projected work ≥ 60% of the turn budget · human flagged token pressure.
**SOLO** otherwise. Tiebreak within one honest re-count → SOLO.

**Mid-run re-gate:** while SOLO, if discovered sites exceed 1.5× inventory, or half the turn
budget is gone with under half the checklist done, plan the REMAINDER (§4.1) and go SWARM.

## §3 · SOLO path

**[RIG]** SOLO means ONE rig worker, not the orchestrator implementing. Write the full
checklist (every site, `file:line`) into one work order, dispatch it (§4.4), then run the same
review loop (§4.7–§4.8). Tiny mechanical jobs within the §0 exception are applied directly
via §4.9.

## §4 · SWARM path

### §4.1 · Plan-as-data

Scratch dir OUTSIDE the repo (`mktemp -d`, or `%TEMP%\orch-<name>`). Write `plan.json` before
any dispatch:

```json
{"mode":"swarm","gate":"GATE line verbatim","rig":"RIG line verbatim",
 "width":"LOCAL-WIDTH line(s) verbatim",
 "workers":[{"id":"W1","nodes":["N01"],"class":"CRITICAL","kind":"REASONED","lane":"rig",
             "files":["lib/log.js"],"deps":[],"spec":"SPEC.md 2.1-2.4",
             "destructive":false,"est_ctx_k":24}],
 "batches":[["W1","W2"],["W3"]],
 "gate_cmd":"<the 4.7 script>"}
```

NOTHING non-product is ever written inside the repo.

**Output diet (your tokens are the expensive ones):** plan.json ≤ ~40 lines; reconciliation
≤ ~30 lines; gate script ≤ ~150 lines; review verdicts ≤ ~8 lines each. Work orders are as
long as they must be — they are the one place spending your tokens saves more later. Do not
narrate between tool calls.

Present the plan (worker table + lanes + batches). Human present → pause for approval;
headless → `PLAN-APPROVED: AUTO`.

### §4.2 · Group into workers, collapse tiers

- One worker per cohesive cluster (~3–8 sites or 1–3 modules). Target 6–12 workers for a
  15–70-site job. **[RIG]** Size so a worker's END-of-run context fits the width math (§4.4).
- Never two writers of the same file in the same batch.
- **[RIG]** Each CRITICAL worker owns ONE contract and is never grouped with non-CRITICAL nodes.
- **Contract-pinned tier collapse:** a dependency pinned by a normative spec (exact
  signatures, values, worked examples) is NOT a batch edge. Only physically-shared,
  unpinned prerequisites create a second batch. **[RIG]** When in doubt, take the extra
  batch: approve the contract, then fan out against the landed file.

### §4.3 · THE MANDATE (the excuses are pre-refuted)

- You do NOT implement. Every node goes to a rig worker (except §0's tiny exception and
  §4.8 step 3). "Quicker to do this one myself" is the defection the arena caught 28/28 times.
- "I hold the full map in context; I'll execute rather than re-fragment it" — the map is
  TRANSMITTED: the work order carries the sites, rules and traps. "It fits in one context" —
  the gate said otherwise. "The local model is too weak for this one" — that is what the
  review loop is for; reject with specifics, and if it keeps failing §4.8 says when you step in.
- Dispatch every ready worker of a batch in ONE foreground Bash call (§4.4). Launch → await →
  launch next is a violation; landing checks run after the WHOLE batch returns.
- **Dispatch tripwire:** GATE printed SWARM and three of your turns passed with no dispatch
  and no §4.9 run → you are mid-defection; write the work orders and dispatch.
- Your turns are for: inventory, plan, work orders, gate, review verdicts, escalation,
  reconciliation.

### §4.4 · Lanes — the rig

**[RIG]** Lane table (roles come from the profile, verified live each run):

| class | executor |
|---|---|
| MUNDANE / MECHANICAL | `coder` lane if usable, else `general` |
| WORKHORSE | `coder` lane if usable, else `general` |
| CRITICAL | `general` lane (the reasoning model), else `coder` |
| DESTRUCTIVE | drafted on `general`, never executed without a live human (§6) |

A lane may carry `"orch_local_role": "general" | "coder"`; absent that, a model id containing
`coder` is `coder`, anything else `general`; one usable lane serves every role. As of
2026-09-17 the profile has one lane, `rig` = `qwen3.8-27b` (general). A Qwen3-30B-A3B-Coder
lane is added to the profile as its own entry and becomes `coder` with no edit here.

**The rig is one shared vLLM engine** (per lane: `max_num_seqs` sequences over a KV pool of
`kv_pool_tokens`). Shared with email triage, Chat, Hermes — past fair share the gateway returns
`429` + `Retry-After` and never queues. Two models on one rig split its GPUs and KV; use each
lane's own profile figures, never the single-model pool.

**Width (computed, printed, obeyed), per lane:**
`LOCAL-WIDTH: <lane> est_ctx=<K> kv_cap=<n> start=<n> max=<n> ready=<n>`
- `est_ctx` = honest END-of-run context of one worker (order + files read + turns + output,
  reasoning included). `kv_cap` = floor(min(0.9 * `kv_pool_tokens`, `width.kv_budget_tokens` when supplied) / est_ctx). Respect the shared-lane reservation and the live model context limit.
  `max` = min(`max_num_seqs`, kv_cap). `start` = min(ready, ceil(max/2)).
- +2 per landed batch with zero `429`s and no timeouts; a worker past `est_ctx` →
  re-estimate, don't widen. `429` → honour `Retry-After`, halve width (floor 1), re-dispatch
  only the refused worker; never counts as a failure.

**Dispatch mechanics.** Per worker:
`bash <profile.launcher> --profile <resolved-profile> --card <archived-full-card> --cwd <repo-root> --lane-id <lane-id> --timeout 3000 --no-harden --run-id <run_id> --node-id <node_id>`
with `CLAUDE_CODE_MAX_OUTPUT_TOKENS` = the lane's `max_output_tokens` (default 8000; 12000 for a
worker emitting a whole module or a large block set). Key from the env var named by
`auth_env` — never in an order, a repo, or a transcript. Orders live outside the repo.
**A batch = ONE foreground Bash call**: all launchers with `&`, each to its own `<order>.out`,
LAST command `wait`. Bash `timeout` 3600000 ms; a call dying near ~570 s means
`BASH_MAX_TIMEOUT_MS` is unraised → lane-unavailable, tell the human. Nothing lands until
every worker returns.

### §4.5 · Work orders (the plan, handed down)

ONE shared preamble, byte-identical across the run (prefix-cache hit):

```
Repo root = your working directory. Your work order is the binding plan. SPEC.md sections
it names are normative — READ them from disk. Touch ONLY your OWNED files.
Global constraints: <task rules>
Self-check before reporting; scratch files OUTSIDE the repo (system temp).
Report EXACTLY:
STATUS: DONE | BLOCKED(<question>)
FILES: <touched, or the blocks file for a MECHANICAL order>
CHECK: <command> -> <result, 1 line>
NOTES: <=3 lines
If any instruction cannot be applied exactly as written: STATUS: BLOCKED. Never guess.
```

Per-worker order: id · class · kind · OWNED files (exact) · upstream state ("X is FINAL on
disk — import it, never modify") · spec sections by reference · done-looks-like · self-check.

- **MECHANICAL order** adds: the rule, 2–3 verbatim before → after examples, exclusions, the
  site list (`file:line`), and "write one SEARCH/REPLACE block per site (format below) to
  `<blocks-file outside repo>`; do not edit files directly." Block format:
  ```
  FILE: <path from repo root>
  <<<<<<< SEARCH
  <exact current lines, byte-for-byte from disk; enough context to be UNIQUE>
  =======
  <replacement>
  >>>>>>> REPLACE
  ```
- **REASONED order** adds: the contract others depend on (signatures, invariants, error text)
  pinned verbatim; how the worker should approach anything you already decided.
- **[RIG] Local orders carry traps explicitly.** Every trap your investigation found in the
  OWNED files is pasted BYTE-EXACT (orderings, "must NOT change" items, error templates), with
  one worked example per distinct call-shape you already know of. You investigated once so the
  worker doesn't have to guess — put what you learned in the order.

### §4.6 · Landing (reports are claims)

After the WHOLE batch returns: `git status --porcelain` + `git diff --name-only`; any change
outside the union of OWNED lists is reverted and noted in that worker's rejection. MECHANICAL
workers' block files go through §4.9 now. No report, a truncated report or a timeout = the
worker did not finish (§4.8). BLOCKED → answer from spec/plan, re-dispatch same lane (does not
count as a rejection).

### §4.7 · The gate (orchestrator-owned, deterministic)

Write your OWN gate script in scratch, from the SPEC, before or while the first batch runs:
import sweep of every touched file · every spec worked example executed with verbatim output
comparison · one end-to-end integration path · anti-regression ("must not change" items
verbatim) · for MECHANICAL rules, a grep for the BEFORE pattern in OWNED files expecting zero
(minus exclusions) · scope sweep. **Exit code decides.** A call-shape with no executable
example is UNCOVERED; say so in reconciliation.

The gate is not answerable to the implementation: failing gate = wrong code until you have
independent evidence the CHECK is malformed. Genuinely broken or blind gate → stop and say so;
never weaken it to pass.

### §4.7a · **[RIG]** The review loop (approve / reject)

Per worker, after landing:

1. **Gate first.** Red → REJECT with the failing gate output (no code reading needed yet
   beyond locating the cause).
2. **Green → review, budgeted.** `git diff --stat` for the worker's files, then:
   - CRITICAL, auth/secrets/input handling, or a worker already rejected once → read its diff.
   - Everyone else → one hunk per call-shape/rule; anything odd in the stat (unexpected size,
     deletions, new files) → read the diff.
   Look for what the gate misses: hardcoded example values, swallowed errors, dead branches,
   ordering hazards, changes that don't match the plan.
3. **Verdict**, one per worker: `REVIEW: <W> APPROVE` or
   `REVIEW: <W> REJECT` followed by a FIX LIST — each item `file:line — what is wrong — what it
   must be`, plus the gate output lines if any. ≤ ~8 lines. Tell the worker WHAT to fix and
   WHERE; do not write the fix.
4. Whenever a rejection reveals something the gate could check, add that check to the gate
   before re-dispatch — the next pass is then gated, not re-read.
5. **Reject → re-dispatch** the same order plus the FIX LIST to the worker's lane, after
   reverting its OWNED files ONLY if the diff is unsalvageable (wrong approach, scope stray,
   timeout/partial return); otherwise the worker fixes on top of its own diff. Rejected workers
   of one batch go out together in one dispatch call.
6. Approved nodes land as local candidate commits (§7.1). Downstream batches dispatch once
   their dependencies are APPROVED.

### §4.8 · Escalation — when the orchestrator steps in

Per worker, counting REJECTs (a `429` or BLOCKED never counts):

1. **Rejections 1–2:** fix list → same lane (§4.7a step 5).
2. **Rejection 3:** revert; re-dispatch FRESH with the full order + accumulated fix lists, on
   the OTHER usable lane if there is one (coder ↔ general), otherwise same lane with the node
   split smaller.
3. **Rejection 4 → STEP IN:** you repair the minimal failing diff in-session, run the gate,
   and log `ORCH-STEP-IN: <W> <reason, 1 line>` in reconciliation.
4. Still failing after your repair → stop that node and report to the human with the order,
   the diffs and the gate output. Independent workers continue; dependents hold.

Whole rig unavailable mid-run → stop and report state. Never fall back to API workers.

### §4.9 · The apply-tier (MECHANICAL nodes)

1. **Blocks come from the rig** (or from you, under §0's tiny exception). SEARCH must be
   verbatim from disk — approximate SEARCH is a defect worse than no diff.
2. **Apply deterministically — no model.** Use `tools/clean/apply_blocks.py` or
   `~/.claude/tools/clean/apply_blocks.py` if present; else a stdlib script in SCRATCH meeting
   the contract: a block applies iff its SEARCH matches exactly once in the evolving in-memory
   file; zero → `nomatch`, ≥2 → `nonunique`; never forced, fuzzed or eyeballed; one write per
   file; line endings preserved, EOL-normalized matches counted separately; reports
   `applied / nomatch / nonunique` + per-block residue; supports `--atomic`.
3. **Residue is a rejection item**, not your job: `nomatch`/`nonunique` blocks go back to the
   worker in its FIX LIST ("re-emit with verbatim, unique SEARCH"). Residue touching auth,
   money, concurrency or migrations is §6.
4. **Gate as always.** A clean apply of a wrong REPLACE is still a failure only the gate
   catches.

### §4.9a · Fleet reuse

The approved block set applies to N targets at ~0 marginal cost. Declare policy first:
`FLEET_POLICY: ATOMIC` (default; mandatory for shared contracts, wire formats, auth, money,
migrations) or `PARTIAL_ALLOWED` (independent edits; residue targets quarantined and named).
Print `FLEET: <policy> targets=<n> clean=<n> residue=<n> quarantined=<list|NONE>`. Unreported
residue = failed run.

## §5 · SOLO gate

Same as §4.7 and §4.7a. The script decides done; review can reject a green gate, never
approve a red one.

## §6 · Destructive interlock

DESTRUCTIVE = schema/data migrations, data deletion or movement, history rewrites/force-push,
deploy/infra mutation, secret or auth-provider changes — anything irreversible outside the
working tree.
- **[RIG]** A `general`-lane worker drafts PLAN + exact commands + diff + rollback; it never
  executes. You verify the rollback restores state.
- A live human approves execution. Headless → `DEFERRED-DESTRUCTIVE` with the ready plan.
- A computed diff touching auth, money, concurrency or migrations is still destructive; the
  apply-tier does not launder it.

## §7 · Reconcile and hand off

- **Requirement matrix:** spec item → IMPLEMENTED / PARTIAL / DEFERRED / SCOPE-CREEP, file refs.
- **Routing table:** worker · class · kind · lane · model · rejections · verdict; planned vs
  actual explained. MECHANICAL: blocks applied/nomatch/nonunique.
- **[RIG] Loop metrics:** first-pass approval rate by class × kind × lane; rejections that the
  gate should have caught (each is a gate gap); `ORCH-STEP-IN` count; `429`s and final widths;
  orchestrator API tokens (the run's only frontier spend); local $ = 0.
- **Gate evidence:** the script's final output tail.

### §7.1 · Commit policy — the only commit rule

| action | approval |
|---|---|
| local candidate commit (not pushed) | none, unless §6 applies |
| push · PR · merge to a shared branch · release · deploy | human, always |
| auto-approve / headless | no commits — leave the tree uncommitted |

One commit per APPROVED node or MECHANICAL cluster:
`[UNREVIEWED][<node>][<CLASS>][RIG-<lane>] <summary>`. No towering commits.

## §8 · Hygiene

After the final gate you MAY run the repo's own lint/unused tooling on the changed surface;
findings go to a rig worker as a work order, not to you. **Security is NOT optional:** any diff
touching auth, sessions, input handling or secrets gets a read under §4.7a before handoff. No
clean phase runs (§9 withdrawn 2026-08-05, unmeasured); `/orch-clean` is a separate, deliberate
invocation: gate → clean → re-gate.

## §10 · The dispatch log (MANDATORY — this is training data, not telemetry)

**Block version — log it verbatim as `skill_version`:** `s10-v11-2026-09-21`

Bump that string whenever this block changes. `skill_version` is THIS block's version, not
the skill's title-line version — they are different facts and the first pilot conflated them
(logged `v5.0.1`, which describes the skill and says nothing about the schema that wrote the
row). Log the skill's own version separately as `skill_title_version` if you want both.

### Where things go

```
log      <workspace>\plexar-telemetry\runs\dispatch-<YYYY-MM-DD>.jsonl
cards    <workspace>\plexar-telemetry\artifacts\<run_id>\cards\<worker>.txt
```

**Use NATIVE WINDOWS PATHS for both.** If your shell is MSYS/Git bash, `/c/Code/...` will
*create a directory* and then any Windows-native tool cannot open it. The first pilot lost
three appends and its own gate script to exactly this.

**And the rule is broader than paths: MSYS rewrites ANY leading-slash ARGUMENT before a
native tool sees it, whether or not it is a path.** Second pilot run, same day:
`aws ssm get-parameter --name /hermes/stt/api-key` returned `ParameterNotFound` because bash
turned the parameter *name* into a Windows path, while the next check read the same parameter
fine from Python. **A check that fails this way is a malformed check, not a failing state** —
repair the check and record it as an `orchestrator_repairs` entry, never as a defect in the
thing being checked. Outside every product repo, and **not
the scratch dir** — scratch is wiped, and a log whose references point into it is a log whose
most valuable field is already gone.

### Cards are FILES, written BEFORE the spawn (this amends §4.5's mechanics)

Before each spawn, write **the full prompt as sent** — shared preamble plus card body — to
`artifacts\<run_id>\cards\<worker>.txt`. Log `brief_path` and `brief_sha256`; do **not** try
to inline the card into JSON.

This exists because `brief_text` is not honestly populatable: the orchestrator has no
programmatic handle on a prompt it already sent, `Agent` returns an id and an `output_file`,
and those transcript files are empty. The only route to verbatim would be retyping a 60-line
card into a JSON string per spawn — premium tokens duplicating text that exists, and exactly
the step a future orchestrator skips silently, producing the summary this schema forbids.
Writing the file first makes verbatim **free**, and the hash makes it checkable.

**HASH THE LF-NORMALISED CONTENT, AND WRITE THE FILE WITH LF.** Measured 2026-09-21 on a live
12-node SWARM: all three `brief_sha256` values failed to verify, 3 for 3 — the orchestrator
hashed the string it held (LF) while Windows wrote the file as CRLF, so
`sha256(string) != sha256(file)` by construction. The cards were byte-perfect; only the
verification was broken. **A hash that silently fails to verify is worse than no hash**,
because whoever joins on it gets zero matches and concludes the cards are wrong. Normalise CRLF to LF before hashing, and write with LF.

**A resumed worker is not a re-spawn.** If you unblock a worker in place (SendMessage,
keeping its context) it received only a delta, not a new card. Write the delta as
`<worker>-attempt<N>.txt`, open it with one line saying it is a delta and not a standalone
card, and set `retry_mode: "resume_delta"`. A fresh spawn with a new card is
`retry_mode: "respawn"`. **Both produce `attempts: 2` and they are completely different
inputs** — conflating them teaches a classifier that a card it never saw caused an outcome.

### Five event types

**`run_start`** — ONE row at INVENTORY, before planning. `run_id` · `skill` ·
`skill_version` · `cwd` · `task_summary`. Exists so an empty `runs\` directory is
unambiguous: no row means no run, rather than "possibly still planning". Costs nothing.

**`plan`** — ONE row at plan freeze: `path` (SOLO|SWARM) · `scale_gate_reason` ·
`node_count` · `lanes_planned` · `efforts_planned` · `edges` · `max_depth` ·
`interfaces_declared` · `interfaces_consumed` · `interfaces_absent_at_dispatch` ·
`diffable_sites` · `generative_sites` · `apply_tier_nodes` · `gate_script_sha256` ·
`preamble_sha256`.

**`dispatch`** — at each spawn, **and once per node on the SOLO path too** (see below):
`node_id` · `worker` · `phase` · `lane` · `effort` ·
`lane_reason` · `brief_path` · `brief_sha256` · `brief_author_model` · `files_owned` ·
`spec_sections` · `diffable` · `retry_mode` · `pred`.

**`outcome`** — when the report lands: `status`
(`DONE|BLOCKED|GATE_FAIL|LADDER_EXHAUSTED`) · `blocked_question` · `blocked_cause` ·
`attempts` · `escalated_to` · `files_touched` · `scope_violation` · **`node_check_cmd`** ·
**`node_check_exit`** · `wall_ms`.

**`run`** — ONE row at landing, `node_id: "RUN"`: **`status`**
(`COMPLETED|HALTED_FOR_DECISION|ABANDONED`) · `gate_exit` · `gate_failing_check` ·
`gate_evidence` · **`gate_verified_against_defect`** ·
**`interfaces_declared_uncalled_at_landing`** · `orchestrator_repairs` ·
`orchestrator_repair_notes` · `wall_ms`.

### `HALTED_FOR_DECISION` — a run that correctly refused to dispatch is still a run

The node statuses (`DONE|BLOCKED|GATE_FAIL|LADDER_EXHAUSTED`) describe work that was
dispatched. **A run that stops at the plan stage to put a decision to the human dispatched
nothing and is none of them** — so before v5 it was unrepresentable, and therefore unlogged.

That is not a gap, it is a **bias in one direction.** Those runs are exactly the cases where
the orchestrator judged the task not ready and asked first — the same judgement a
brief-quality classifier exists to make. **Train on data that excludes them and the model
never learns to recommend stopping, because it has never seen stopping rewarded.**

* `COMPLETED` — the gate ran and the run landed.
* `HALTED_FOR_DECISION` — stopped before dispatching to put a choice to the human. Write the
  `plan` row with whatever the assessment produced, and record the question in
  `gate_evidence`. **This is a legitimate and often correct outcome; log it as one.**
* `ABANDONED` — stopped for any other reason. Say why in `gate_evidence`.

Found 2026-09-21: an `/orch-code-anth` run assessed a PDF-builder request, proposed a design,
and stopped because the approach changed the data model. Best judgement in the transcript,
and it wrote zero rows.

### `gate_exit` is a RUN field. Nodes carry `node_check_exit`.

§4.7 mandates ONE gate script for the run, so a per-node `gate_exit` is **structurally null
forever** — the first pilot had it null on 6 of 7 outcome rows, which made the KPIs
uncomputable as specified and forced them to be read off `status`, which `kpi.md` forbids.

The per-node signal already exists: §4.5 requires every worker report
`CHECK: <command> -> <result>`. Log that command and its exit as `node_check_cmd` /
`node_check_exit`. The run's gate exit goes on the `run` row, where the evidence actually is.

### `gate_verified_against_defect` — three states, never two

**When a node exists because a specific defect escaped, run the gate once against the
REINTRODUCED defect before calling the run green.** A gate nobody has seen fail is an
untested instrument, and §4.7 stakes everything on the exit code meaning something. The first
pilot did this in two minutes and it is the only reason "the suite observes the bug it names"
is a measurement rather than a claim.

- `true` — defect reintroduced, gate failed, defect restored, suite green again.
- `false` — not attempted. This is a gap, and it should look like one.
- `"not-reproducible-in-harness"` — the defect genuinely cannot be reintroduced in a test
  (needs a real WebView, a sub-frame race, a stale cookie). **A binary field would silently
  convert "I could not verify this" into "I did not bother", which inverts its purpose.**

### `blocked_cause` — and it must cover guidance that MISLEADS, not only guidance that BREAKS

Every BLOCK gets one of:

- `brief` — the card was genuinely silent or wrong. **The only value a brief-quality
  classifier should train on as a positive.**
- `orchestrator-broken` — the orchestrator broke the node's target between batches. The
  worker was right to refuse.
- `orchestrator-misleading` — the guidance compiled, was accurate enough to act on, **and was
  still materially wrong.** The first pilot's own unblocking delta placed a call in a class
  whose dependency is null in production: it would have passed every test and been a no-op on
  the real device. **A card that compiles and misleads is the more dangerous of the two** and
  no test or gate will find it.

Without this field, every mid-run orchestrator repair depresses the exact number a
brief-quality classifier trains on, charging workers for the orchestrator's mistakes.

### `interfaces_*` — typed, and checked at BOTH ends

Each entry is `{kind, name, path}`, `kind` one of:
`function` · `method` · `channel` · `http_route` · `env_var` · `payload_shape` · `cli_flag` ·
`config_key`. The first pilot hit five kinds in one run, and because
`interfaces_absent_at_dispatch` is set arithmetic over free text, it came out `[]` **only
because the same spellings happened to be chosen at both ends.** Untyped, this field reports
success by luck.

Two checks, neither needing a model:

- **`interfaces_absent_at_dispatch`** (plan row) — consumed but not on disk and not produced
  by an earlier tier. A failure prediction from pure set arithmetic.
- **`interfaces_declared_uncalled_at_landing`** (run row) — one grep per declared interface
  after the batch. Catches **built-but-never-wired**: the first pilot had an interface in
  `interfaces_declared` AND `interfaces_consumed`, both ends built, and **zero call sites**,
  because no consumer's card mentioned it. Shipped, that ack's deadline would have expired on
  every SUCCESSFUL locked turn and reported failure on the exact case it was built to
  confirm. **Worse than omitting it**, and it survives green worker reports and a green gate.

**Consequent rule on §4.5:** an interface in `interfaces_declared` must appear in at least one
**consumer's** card, not only its producer's. A promise nobody was told to call is not wired.

### SOLO writes dispatch rows too, or its outcomes are untrainable

**On the SOLO path the orchestrator IS the worker, and it still writes one `dispatch` row per
node** — `worker: "self"`, `lane: "none"`, `lane_reason` recording why SOLO was chosen for
this node, and `brief_path` pointing at the intent written to a card file exactly as a spawn
would.

**`effort` IS THE EFFORT ALONE — never a model/effort pair.** On a `self`/`none` node there is
no worker model, and orchestrators have been filling `effort` with their OWN capability as
`"opus/low"`. That information is worth keeping, but writing it there destroys the field:
`"opus/low"` is not comparable to `"low"`, so those rows drop out of the one analysis `effort`
exists for. Write `effort: "low"` and put the orchestrator's own model in
**`orchestrator_model`**. Measured 2026-09-21: 5 rows were lost this way before the field was
split.

The second pilot run was SOLO and produced **three `outcome` rows and zero `dispatch` rows**.
That leaves outcomes with **no corresponding input**, which breaks the (input, outcome) pairing
this entire log exists to produce: an outcome nobody can attribute to a brief teaches a
classifier nothing. **A SOLO run that logs only outcomes has logged nothing trainable.**

### The field rules

- **`ts` IS ISO-8601 WITH A UTC OFFSET, ALWAYS** — `2026-09-21T11:01:45-04:00`, never a
  naive `2026-09-21T11:01:45`. Measured 2026-09-21: 40 of 91 rows carried no timezone at
  all, and because the host's own zone was changed from `Etc/UTC` to `America/New_York`
  mid-day, **some naive stamps are UTC and later ones are local — in the same field.** Any
  ordering or cross-log join on `ts` is then silently wrong by up to four hours, with
  nothing to signal it. A timestamp without an offset is not a timestamp.

- **`brief_path` + `brief_sha256`, never a summary.** The card is the input half of every
  (input, outcome) pair. If you find yourself paraphrasing, the file step was skipped.
- **`brief_author_model` is who WROTE the card, not who ran it.** Without it, a bad card and a
  bad card-*writer* are indistinguishable and anything trained on this averages a confounder.
- **`effort` is a separate axis from `lane`.** The target is `(brief, model, effort) ->
  P(success)`; effort is the cheap dial that turns a BLOCKED into a DONE without moving tier.
- **`lane_reason` is a forcing function, not bookkeeping.** Measured: writing "contained
  native change against a pinned name; no new concurrency beyond one cancellable deadline"
  demoted a node from opus to sonnet *while it was being written*. Write the clause that
  decided it, not the tier.
- **`blocked_question` verbatim** from `STATUS: BLOCKED(<question>)` — the label for which
  field the brief omitted, in the worker's own words.
- **`files_owned` vs `files_touched`** — the landing protocol already computes this diff to
  revert strays; recording it turns enforcement into a free label.
- **`orchestrator_repairs` is mandatory, including zero.** If the log cannot see the
  orchestrator's own defects it will systematically attribute them to workers. The first
  pilot had three, and **all three would have passed both the worker reports and a green
  gate.**
- **`node_check_exit: null` is not `0`.** A check that did not run is not a check that passed.
- **`pred` is expected-null until a classifier exists.** Nulls here are the designed state at
  row 0, not missing data. Absent predictions are `null`, **never `0.0`** — a missing opinion
  and a confident zero are opposite claims. The rubric carries no `p_success` at all: it is a
  decision table, and inventing one would make the comparison dishonest.

### Rig-dispatched workers carry the join on the WIRE (contract §10h)

Everything above assumes the worker was spawned through the `Agent` tool, where a
`PreToolUse` hook can capture the dispatch deterministically. **`/orch-code-local`
dispatches over HTTP to the rig instead, so no hook fires and this log is the only
record** — a self-report, in a dataset whose premise is that reports are claims.

Plexar's gateway now records the join itself. **Every request a rig worker makes must carry
three headers:**

```
X-Plexar-Orch-Run:     <the run_id from this log>
X-Plexar-Orch-Node:    <the node_id>
X-Plexar-Brief-Sha256: <the SAME LF-normalised hash logged as brief_sha256>
```

They land in `requests.orch_run_id` / `orch_node_id` / `orch_brief_sha256`, so a row in
plexar's own `requests` table joins to this log's dispatch row, and through
`brief_sha256` to the exact card on disk. **That makes the X side verifiable on the rig
path instead of merely asserted** — plexar hashed what it received, you hashed what you
wrote, and a mismatch is a finding rather than a silence.

**THE BRIEF IS NEVER SENT IN A HEADER — ONLY ITS HASH.** Plexar stores no prompt text for
this, which is why the join works with `PLEXAR_CAPTURE_PAYLOADS` off. Arming payload
capture to correlate a run would trade consumer prompt text for a 64-character string you
already have.

All three are OPTIONAL to plexar and rejected if malformed (bounded charset, 128 chars;
the hash exactly 64 hex). **A rejected value is recorded as NULL, never truncated** — a
truncated id would join this run's request to a different run's dispatch. So send them
correctly or not at all; a wrong one is worse than a missing one.

**`capture` HAS THREE VALUES, AND SENDING THE HEADERS EARNS ONLY THE MIDDLE ONE.**

* `gateway_verified` — the gateway **stored** the correlation and you CONFIRMED it (the
  `orch_*` columns exist and the row is there). This is the only value that asserts
  verification, so it requires evidence, not intent.
* `headers_sent_unconfirmed` — the headers went out; nothing confirmed receipt.
* `self_reported` — no headers were sent at all.

**Found 2026-09-21, and it is the exact failure this field was invented to prevent.** The
local launcher was wired to send the headers and wrote `gateway_verified` for doing so —
while the rig's gateway was running pre-§10h code that **parses none of them, has no columns
for them, and silently discards them**. Two rows therefore claimed a verification that never
happened. Nothing was wrong with the sender; the receiver was two commits behind, and
"I sent it" had been allowed to mean "it was recorded".

**A provenance label that can be earned by intent rather than evidence is worse than no
label**, because it launders unverified rows into the verified class and a classifier trained
across them cannot tell which inputs were checked. `gateway_verified` is claimable only after
the §10h migration is deployed AND a row has been read back.

Two provenance classes that look identical in the data are one class of silent error.

**Normalise `cwd` before grouping on it.** Codex writes `C:/Code/...` and Claude writes
`C:\Code\...` for the same directory, so a group-by on the raw value splits one repo in two.
Record it as sent; normalise at read time.

### Shadow mode, and the arm that keeps it honest

**Predictions gate NOTHING until one beats the §4.4 rubric on held-out data.** When one is
promoted it **amends the brief and discloses the amendment — it never refuses**; refusing on a
probability invents a new failure mode, stalling work that would have succeeded.

**The 10% exploration arm is permanent.** Always dispatch ~10% of briefs a promoted classifier
would reject, flagged `exploration: true`, and log their outcomes. A `rejected` row records
the PREDICTION only; without the arm, false rejections produce no outcomes, stay invisible,
and the classifier drifts into refusing valid work with rising confidence.

**The bound: a classifier is the source of truth about PREDICTED SUCCESS, never about
CORRECTNESS.** `Exit code decides` (§4.7) is untouched by anything in this section.

### Operational

**BUILD THE ROW WITH A JSON SERIALISER — NEVER BY STRING CONCATENATION.** Every `cwd`,
`brief_path` and `files_owned` entry on Windows is full of backslashes, and `C:\Code` hand-written
into a JSON string is an **invalid escape** that corrupts the line. Measured 2026-09-21: one
`run_start` row was destroyed exactly this way, while the other 55 lines that day were valid —
which is worse than consistent failure, because it looks healthy until a path appears. Use
`json.dumps` (or your language's equivalent) and let it escape.

**Append one line and close. Never read-modify-write** — spawns may append concurrently, and a
read-modify-write loses rows. This also means a corrupt line must be left in place rather than
edited out while runs are live: repairing one row is not worth risking the ones arriving.

**Logging NEVER fails the run.** Unwritable path → note it in reconciliation and continue. A
run that dies because telemetry failed is worse than a run with no telemetry.

**This invalidates the published cost-per-successful-run figures for this skill.** Re-take
them, segmented by `skill_version`, before citing any of them.

**The three KPIs this exists to produce**, computed from `node_check_exit` and the run row's
`gate_exit` — never from `status`, because reports are claims: **first-try DONE rate** ·
**mean attempts per node** · **self-report-vs-gate disagreement rate**. Exclude BLOCKs whose
`blocked_cause` is not `brief` from the first two, or every orchestrator repair depresses the
number a classifier trains on. Zero point, first pilot, 2026-09-21: **4/5 first-try, 1.2 mean
attempts, 0/6 disagreement** — with one BLOCK charged to the orchestrator, so read it as
indicative, not as a baseline.

## Invariants

- This file is complete; an unresolvable cross-reference is a defect to report.
- **[RIG]** The API seat is the orchestrator only. No API workers, no API fallback. Rig down →
  stop and tell the human.
- **[RIG]** Investigate once; the plan and work orders carry what you learned. Execution — both
  MECHANICAL and REASONED, CRITICAL included — is the rig's. You write code only under §0's
  tiny exception or §4.8 step 3.
- **[RIG]** Every worker loops DONE → gate → review → APPROVE | REJECT(fix list) until approved;
  review can reject a green gate, never approve a red one.
- One writer per file per batch. Specs are read from disk by whoever implements.
- Worker reports are claims; the gate is evidence.
- Local dispatch is foreground, parallel within the printed width; every worker returns before
  landing; `429` halves width and never counts as a rejection.
- SEARCH is verbatim or invalid; residue is never forced; fleets declare policy, ATOMIC default.
- DESTRUCTIVE is drafted, never executed without a live human.
- Nothing non-product in the repo. §7.1 is the only commit rule.
- Report cost per SUCCESSFUL run. A new rig model is a new arm cell, not a silent upgrade.
- The dispatch log (§10) is mandatory, zeros included. Cards are FILES written before the spawn; `gate_exit` is a RUN field and nodes carry `node_check_exit`; a BLOCK without a `blocked_cause` charges the orchestrator's defects to workers. Logging failure is never run failure.
