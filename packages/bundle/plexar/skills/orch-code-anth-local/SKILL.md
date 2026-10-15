---
name: orch-code-anth-local
description: "Plexar orchestration skill /orch-code-anth-local: v5.0.1-LOCAL (v5.0.1 + the rig's 16 sequences: residue-apply · overflow volume)"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-code-anth-local.md"
  source_sha256: "ce76ae7587ff293e4879eaf8dc2d717e91413e7d98d7e49c0c8bb372c3413803"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-code-anth-local — v5.0.1-LOCAL (v5.0.1 + the rig's 16 sequences: residue-apply · overflow volume)

> ### §10 FIRES AT FIVE POINTS IN THE FLOW BELOW — NOT AT THE END WHERE IT IS WRITTEN
>
> `run_start` at **inventory** · `plan` at **plan freeze** · `dispatch` at **every spawn AND
> every SOLO node** · `outcome` when **each report lands** · `run` at **landing**.
>
> §10 is mandatory and it is the last section in this file purely for readability. **A run
> that reaches the inventory and writes nothing has already lost data that cannot be
> recovered afterwards** — the 2026-09-21 PDF-builder run did exactly that, because §1 said
> nothing about logging and §10 sat 420 lines later. **Read §10 before acting on §1.**


STATUS: **PROPOSED bench arm, NOT LIVE.** Same graduation bar as any arm: arena k=25 before
it displaces the plain `/orch-code-anth`.

**What this file is (2026-09-14).** The complete `/orch-code-anth` v5.0.1 text, with the
local-lane rules from v4.1-LOCAL and the v5.0-LOCAL overlay folded INTO the sections they
govern. The previous file was a 40-line overlay that named itself as its own "base loop" —
the v4.1-LOCAL base it meant had been overwritten, so the local rules survived only in a
backup. That is the exact self-containment defect v5.0.1 was cut to fix. Every local rule is
now written here; nothing is deferred to another document. Local additions are marked
**[LOCAL]**. Every unmarked rule is v5.0.1 verbatim.

**[LOCAL] The mode.** The owner's maximum-token-displacement mode: the Anthropic API carries
ONLY judgment (this orchestrator seat plus the CRITICAL lane); model-requiring WORKHORSE and
MUNDANE volume runs on the Plexar rig — one shared vLLM engine batching **16 sequences** at
once (§4.4). It still TRADES WALL-CLOCK FOR TOKENS: a 27B on a shared rig is slower per worker
than the API, and the rig's other consumers own part of those 16. But local workers now run
IN PARALLEL up to a computed width — the old "1-deep queue, drain sequentially" rule belonged to
LM Studio on one desktop card and is void here. Use this mode when token pressure outranks the
clock: background, overnight, quota-guard. For speed, use `/orch-code-anth`.

**[LOCAL] Why v5.0 narrows the local lane's job.** Under v4.1-LOCAL a local model had to
INTERPRET the spec to apply DIFFABLE fan-out; measured, the local 30B scored 0/12 on
trap-dense migration slices that way. Under v5.0 the DIFFABLE apply
is DETERMINISTIC (§4.9): **no local model is on the DIFFABLE critical path at all.** The local
lane's honest remaining roles are exactly two: (1) **residue applier** for §4.9 blocks that
came back `nomatch`/`nonunique`; (2) **overflow volume** for GENERATIVE WORKHORSE/MUNDANE
clusters that genuinely fit its window. Never CRITICAL, never DESTRUCTIVE.

Count the work, print a SOLO/SWARM verdict, obey it. Split the work into DIFFABLE
(expressible as verbatim text swaps) and GENERATIVE (everything else). Compute the
DIFFABLE changes yourself and let a deterministic applier land them — no worker model in
the mechanical path. Gate on a deterministic check, never on a model's opinion.

**Operating principle.** The orchestrator is the brain. When it already understands the
exact change, it pushes that change out as data rather than delegating the *understanding*
to a worker. Application of a verbatim diff is deterministic — it does not need a model.

**Self-containment rule.** Everything this skill requires you to do is written HERE. If you
find yourself reasoning "the rule is in another document I don't have, so I'll infer it,"
that is a defect in this file — report it. Do not invent the missing rule.

You are the ORCHESTRATOR: Opus-class judgment at the top, the cheapest model that clears
the gate underneath. Your spend follows your typing. Objective order when they conflict:
**correctness → premium-token displacement → wall-clock → raw dollars.**

**Orchestrator effort.** Two configurations, pick by the job. `opus / high` when ONE PASS
MUST LAND with no retry loop. `opus / low` — the DEFAULT — when a deterministic gate plus
the §4.8 escalation ladder are watching, which is this skill's own operating mode: at the
bottom of the ladder the orchestrator simply executes the computed plan without paying for
deliberation the skill already did. `medium` is price-dominated — never park in the middle.
`xhigh` over-thinks. Workers: the card is the quality mechanism; the model only buys
wall-clock.

*Measurements, corrections and known limits are deliberately NOT in this file. If the bench
repo is present they are in `team/bench/results/` (`V4_FINDINGS.md`, `ROUND3_FINDINGS.md`,
`V5_LIVE_FINDINGS.md`) and Agents-Public `FINDINGS.md` (its own sections 4.7 and 4.7a —
not this file's §4.7); published at
<https://boord-its.com/skills>. Those pointers are evidence, not instructions — this file
is complete without them.*

---

## §0 · The apply-tier gate (decide after §1, before choosing SOLO/SWARM)

After the §1 inventory, ask one added question of the work: **is a node's change
EXPRESSIBLE as localized, verbatim text swaps against files that already exist?**

- **DIFFABLE** — logging/API migrations, signature threading, rename sweeps, config edits,
  mechanical refactors: the change is N independent site-edits with a computable
  before/after. These are the apply-tier's target.
- **GENERATIVE** — new files, structural rewrites, algorithm design, anything whose output
  isn't a swap against existing text. A model implements these; the apply-tier does not
  apply.

Print: `APPLY-TIER: <DIFFABLE n=<sites> | GENERATIVE | MIXED c=<diffable>/<generative>>`

MIXED is normal: the CRITICAL/GENERATIVE core (e.g. a shared contract rewrite) is
implemented by an opus worker per §4.4; the DIFFABLE fan-out (the dozens of call-site
migrations that depend on it) routes to the apply-tier. This is the same split §4.2 already
draws between the pinned-contract core and its downstream sites — the apply-tier just makes
the downstream deterministic instead of a worker swarm.

## §1 · Inventory (mandatory, before choosing anything)
**→ FIRST, before anything below: write the `run_start` row (§10).**


**[LOCAL] STEP ZERO — your literal FIRST tool call, before reading anything:**

```
sh -c 'cat "$LOCAL_LANES_PROFILE" 2>/dev/null || cat ./local-lanes.json 2>/dev/null || echo PROFILE-MISSING'
```

Profile printed → check it is CURRENT before trusting it: its endpoint must be the rig
gateway and answer `/v1/models` with its model `serving` (§4.4). A profile naming LM Studio,
`:1234`/`:1235`, a desktop `127.0.0.1` engine, `max_concurrent: 1` or a RAM lane predates the rig
and is STALE — treat it exactly as `PROFILE-MISSING`, and tell the human. Current profile →
its lanes are §4.4's local executors for this run. `PROFILE-MISSING` →
this file behaves as PLAIN v5.0.1 for the entire run: the API lane table replaces the local
executors and EVERY other rule still binds — a SWARM verdict still means DISPATCH via the
`Agent` tool; solo is not the fallback, the API swarm is. Interactively, tell the human the
profile is missing. Do not re-litigate this mid-run.

Read the task and the spec/source. COUNT the real work — do not estimate from the prompt
alone:

- **sites** — individual edit/creation points (grep the call sites; list the stubs)
- **files** — files you must create or modify
- **read volume** — bytes of code/spec that must actually be read (`wc -c`, ÷4 ≈ tokens)
- **nodes** — discrete deliverables, labeled by RISK (not size):
  - **CRITICAL** — shared contracts others import · auth/security · money math ·
    concurrency · migrations · anything DESTRUCTIVE (§6)
  - **WORKHORSE** — contained implementation against a clear spec · trap-dense edits
  - **MUNDANE** — mechanical, fully specified, judgment-light

## §2 · Scale gate (computed — print the verdict, then obey it)

Print one line: `GATE: SOLO|SWARM — sites=<n> files=<n> read≈<n>K nodes=<n> mix=<C/W/M>`

**SWARM** if ANY of:

- sites ≥ 25, or files to create/modify ≥ 12
- nodes ≥ 12 AND ≥ 40% of them are MUNDANE+WORKHORSE (displacement value exists)
- read volume ≥ 150K tokens, or projected work ≥ 60% of the session's turn budget
- the human flagged premium-token pressure

**SOLO** otherwise — that is the measured optimum below these lines, not laziness.

**Tiebreak:** when a count sits within one honest re-count of a line (e.g. 9 vs 10
deliverables), take SOLO — below the wall the cheaper error is under-routing.

**Mid-run re-gate (the insurance the monolith lacks):** while SOLO, if you reach half the
turn budget with less than half the checklist done, or discovered sites exceed 1.5× your
inventory, STOP — write the plan (§4.1) for the REMAINDER and switch to SWARM.

The apply-tier does not change WHEN to swarm — it changes HOW the DIFFABLE portion of the
work is executed.

## §3 · SOLO path

Do the work in-session with the discipline that survives the wall: write the full checklist
first (every site, `file:line`), execute in file-order batches, tick each site off, re-grep
after each batch to catch missed sites, then run the §5 gate. Interactively, you may
instead hand the whole job to ONE domain specialist when the main context is precious —
brief per §4.5, same gate.

If the SOLO job is DIFFABLE and large, use the apply-tier (§4.9) on yourself: compute the
blocks, apply deterministically, gate. That is where the apply-tier's speed and cost win
shows up even without a swarm.

## §4 · SWARM path

### §4.1 · Plan-as-data

Create a scratch dir OUTSIDE the repo (`mktemp -d`, or `%TEMP%\orch-<name>`). Write
`plan.json` there before any implementation:

```json
{"mode":"swarm","gate":"GATE line verbatim",
 "workers":[{"id":"W1","nodes":["N01"],"lane":"opus","files":["lib/log.js"],
             "deps":[],"spec":"SPEC.md 2.1-2.4","destructive":false,"apply_tier":false}],
 "batches":[["W1","W2"],["W3"]],
 "gate_cmd":"<the 4.7 script>"}
```

NOTHING non-product is ever written inside the repo — no plan, no scratch, no gate script,
no self-check artifacts. The repo receives product code only.

**Output diet (your tokens are the expensive ones):** plan.json ≤ ~40 lines; each worker
card ≤ ~12 lines beyond the shared preamble; reconciliation ≤ ~30 lines; gate script
focused (contracts + named traps + spot-sites + one integration path, ≤ ~150 lines) — the
per-worker CHECKs already covered the breadth. Do not restate preamble content in cards; do
not narrate between tool calls.

Present the plan (worker table + lanes + batches). If a human is present, pause for
approval; in auto-approve/headless mode print it and proceed (`PLAN-APPROVED: AUTO`).

### §4.2 · Group into workers, collapse tiers

- **One worker per cohesive cluster** — a subsystem/file family of ~3–8 sites or 1–3
  modules — NOT one worker per graded requirement. Target 6–12 workers for a 15–70-site
  job. Never two writers of the same file in the same batch.
- **Group WITHIN a lane, never across lanes.** Folding a MUNDANE node into a sonnet or opus
  worker silently up-lanes it — that is where the haiku lane went in v4.0. A worker whose
  nodes are all MUNDANE runs on `haiku`; promoting it to sonnet requires a trap you can NAME
  in that worker's own files, named in plan.json.
- **Contract-pinned tier collapse:** a dependency whose interface is pinned by a normative
  spec (exact signatures, values, worked examples) is NOT a batch edge — downstream workers
  code against the pinned contract while the upstream is built in parallel. Only
  physically-shared prerequisites (foundation modules everyone imports, with no pinned spec)
  create a second batch. Most swarms are 1–2 batches; minimize the critical path — two
  correct plans can differ 2x in wall-clock.

### §4.3 · THE MANDATE (hard rule on this path — the four excuses are pre-refuted)

- You do NOT implement GENERATIVE work. Every such worker is dispatched via the `Agent`
  tool. "It's quicker to just do this one myself" is the defection the arena caught 28/28
  times.
- "Spec fidelity" is preserved by the brief plus the worker reading the spec FROM DISK — not
  by hoarding the work. "It fits in one context" is answered by the gate, which already said
  SWARM. "Per-node briefing cost" is answered by grouping (§4.2) and the shared preamble
  (§4.5).
- Dispatch every ready worker of a batch as parallel `Agent` calls in ONE message — all the
  tool calls in the SAME assistant turn (≤ ~10 per message; split larger batches).
  **Spawning one worker, awaiting its result, then spawning the next is a mandate violation,
  not prudence** — v4.0 did exactly that 10/10 times and turned the swarm into a relay race.
  There is nothing to check between same-batch spawns: landing checks (§4.6) run after the
  WHOLE batch has returned, never between spawns.
- Pass `model` EXPLICITLY on every spawn — never inherit. Put the worker id and node ids in
  `description` (e.g. `"W3 N04-N07 mundane sweep"`) so routing is auditable.
- **[LOCAL] Local workers are the ONE sanctioned exception to the `Agent`-tool rule** — they
  are dispatched through the profile launcher (§4.4). Criticals still go through `Agent` with
  explicit `model`, launched in the same turn as the batch's local launcher call.
- **[LOCAL] The fourth excuse, caught verbatim in this arm's first arena run:** "I hold the
  full call-site map in context now; I'll execute directly rather than re-fragmenting the trap
  knowledge." Pre-refuted: the map is TRANSMITTED, not lost — the trap warnings in each card
  ARE the map, and card-carried traps measurably survive transmission. Measured swarm
  correctness equals solo correctness, so invoking correctness to skip routing is the
  defection. Long local walls are not an excuse either: slow-and-$0 is this mode's purpose.
  (DIFFABLE work is different and not a defection: you compute blocks and the applier lands
  them, §4.9.)
- **[LOCAL] Dispatch tripwire:** if the GATE line printed SWARM and three of your turns have
  passed with no worker dispatched and no apply-tier run, you are mid-defection — stop,
  write the cards, dispatch.
- Your own turns are reserved for: inventory, the plan, briefs, computing apply-tier blocks,
  reading reports, landing checks, the gate, escalations, reconciliation.
- **The apply-tier is not an exception to the mandate.** It is deterministic execution of
  work you have FULLY computed as verbatim data, which is categorically different from
  quietly doing a worker's judgment job. If you are making judgment calls while "applying,"
  you are implementing — dispatch it.

### §4.4 · Lanes (rubric, decided once in the plan)

| capability class | tier | model alias | goes there |
|---|---|---|---|
| CHEAP | MUNDANE | `haiku` | mechanical and fully-ruled, WITH the exact rules and trap warnings in the card |
| WORKHORSE | WORKHORSE | `sonnet` | contained implementation; also trap-DENSE mundane clusters |
| CRITICAL | CRITICAL | `opus` | shared unpinned contracts, auth, money, concurrency, destructive |
| DETERMINISTIC | DIFFABLE fan-out | *(none)* | orchestrator computes blocks → §4.9 applier. No model. |

**[LOCAL] The local lane is ONE shared engine with 16 SEQUENCES — not a queue of one.**
Verify on the day, never from memory: `curl -H "Authorization: Bearer $KEY" <endpoint>/v1/models`
must list the profile's model with `plexar.state: serving`. Facts as of 2026-09-14 (sources:
live `/api/status` + `/v1/models`; the 16 from the running container's argv, board
`llm-NOTE-242` / `llm-DEC-246`):

- **Engine:** the Plexar rig — vLLM, `qwen3.8-27b` (moved to FP8, owner 2026-09-14), tensor-parallel across two
  3090s, `max_model_len` 131,072, MTP speculative decoding. Reached ONLY through the gateway
  `https://llm.plexar.tech` (Bearer key; OpenAI `/v1/chat/completions` and Anthropic
  `/v1/messages` both served). There is no engine on this desktop; `127.0.0.1:8760`, `:1234`
  and `:1235` here are retired and a profile naming them is STALE (treat as `PROFILE-MISSING`).
- **`max_num_seqs = 16`.** vLLM continuous batching runs up to 16 sequences through the GPUs
  at once; the 2nd through 16th are nearly free in compute. The gateway derives its admission
  capacity from that same number (sum of `max_num_seqs` over serving instances). A local
  "lane" is therefore **a slot in that batch**: up to 16 workers can generate simultaneously.
- **The old concurrency law is VOID for this engine.** "One job per lane; parallel slots lose
  to sequential" (measured 2026-07-19/20) was a property of LM Studio on one desktop card. vLLM
  measured the opposite: concurrent requests are all accepted and batched, none refused.
  Draining local workers one at a time on this rig wastes the hardware it was built on.
- **The KV pool is ~333K tokens** (owner's sizing table after the FP8 move, 2026-09-14 — the
  owner's figures, not re-measured here). What fits, per that table:

  | load | fits? |
  |---|---|
  | 16 workers × 20K (prompt + output) | yes, ~96% of the pool |
  | 16 workers × ~20K with a shared prefix | yes, room to spare |
  | one 131K session + 10 workers × 20K | yes, ~331K — at the edge |
  | 2 sessions at full 131K | yes (2.54 fit) |
  | 16 workers × 32K | **no** (512K) — expect preemption pauses |

- **16 is reachable, but it is still a ceiling — three things bind:**
  1. **Shared.** The same 16 serve every Plexar consumer (email triage ~8,800 req/day, Chat,
     Hermes). Your key gets a **fair share**, not the engine: past it the gateway holds briefly
     then answers `429` + `Retry-After`. It never queues for you.
  2. **KV is the real budget: ~333K tokens, divided by what each worker HOLDS.** An agentic
     worker's context GROWS every turn, so size by its END-of-run context, not its first
     prompt. Preemption is recomputed work — past the pool, width buys pauses, not throughput.
  3. **Thinking model.** Reasoning tokens are output tokens; they occupy KV like any other.

**[LOCAL] Dispatch width (computed, printed, obeyed).** Print
`LOCAL-WIDTH: est_ctx=<K> kv_cap=<n> start=<n> max=<n> ready=<n>` in plan.json and the reconciliation.
- `est_ctx` = your honest estimate of one worker's END-of-run context (card + files it reads +
  turns + output). `kv_cap` = floor(**300K** / est_ctx) — 300K, not 333K, leaves ~10% for the
  rig's other consumers. Examples: 20K → 15, 32K → 9, 64K → 4.
- `max` = min(16, kv_cap). `start` = min(ready local workers, ceil(max / 2)).
- Widen by 2 per landed batch while the batch saw **zero** `429`s and no worker timed out, up to
  `max`. A worker that ran past `est_ctx` means the estimate was wrong: re-estimate before the
  next batch rather than widening.
- **Any `429`:** honour `Retry-After`, halve the width (floor 1), re-dispatch only the refused
  worker. A `429` is the gateway doing its job, not a lane failure — it does not climb §4.8.
- Every local dispatch sets `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000` (or 12000). The window is no
  longer the reason (131k now); **KV is** — an unbounded output reservation is exactly the
  per-sequence hold that drives preemption for every consumer on the rig.

| capability class | executor in this mode | goes there |
|---|---|---|
| CHEAP | a rig sequence (fallback `haiku`) | GENERATIVE mechanical work, fully ruled, traps pasted byte-exact (§4.5) · §4.9 residue blocks |
| WORKHORSE | a rig sequence (fallback `sonnet`) | GENERATIVE contained implementation; trap-dense mundane clusters |
| CRITICAL | `opus` — API, ALWAYS | shared unpinned contracts, auth, money, concurrency, destructive |
| DETERMINISTIC | *(none)* | DIFFABLE fan-out → §4.9 applier. Never a local model. |

CHEAP and WORKHORSE share ONE model now; they differ in card density and escalation fallback,
not in executor. (The desktop RAM overflow lane is retired with LM Studio.) Model id, endpoint
and launcher come FROM THE PROFILE — never hardcode them; the facts above tell you what a
current profile must say. **CRITICAL never runs local, no exception**; the demotion rule below
demotes only to API `sonnet`, never to a rig sequence. Report local $ as 0 in reconciliation —
never quote the CLI's fictional local dollars.

**[LOCAL] Dispatch mechanics.** One launcher call per worker:
`bash <profile.launcher> --card <card-file> --cwd <repo-root> --lane-id <lane-id> --timeout 3000`.
The key comes from the environment (`PLEXAR_BENCH_KEY` or the profile's named variable) —
never in a card, a profile committed to a repo, or a transcript. Card files live OUTSIDE the
repo. **A batch of W workers is ONE foreground Bash call** that starts W launchers and ends in
`wait` (`for c in ...; do bash <launcher> --card "$c" ... > "$c.out" 2>&1 & done; wait`), with
each worker's report in its own file. Parallel INSIDE the call; foreground AS a call — a
backgrounded launcher once let a run grade and exit while workers were still writing, and in
headless mode turn-end IS exit, so the call's LAST command must be the `wait`. Pass the Bash
tool's `timeout` explicitly at 3600000 ms (the environment must raise `BASH_MAX_TIMEOUT_MS`; a
call dying near ~570 s means the cap is unraised — treat it as lane-unavailable and say so).
Workers in one batch still obey one-writer-per-file (§4.2). The run is not done — no landing,
no gate, no reconciliation — until every dispatched worker has returned.

The capability class is the architecture; the alias is today's mapping. When you change
which model wears a jersey you have changed the mapping — not the algorithm — and the
numbers behind the mapping do not carry.

**Demotion rule:** a CRITICAL-labeled node whose behavior is fully pinned by the spec
(signatures + values + worked examples) MAY run on `sonnet` — but NEVER auth, money,
concurrency, or destructive nodes. **Promotion rule:** a mundane cluster dense with
anti-mechanical traps runs on `sonnet`. `subagent_type: general-purpose` always works; a
matching domain specialist is fine too — the explicit `model` still governs.

**Pinned generation.** Spawns use tier aliases (the `Agent` tool accepts only
haiku|sonnet|opus|fable), but every number in the evidence files describes ONE pinned
generation — **G1**: haiku=`claude-haiku-4-5-20251001`, sonnet=`claude-sonnet-5`,
opus=`claude-opus-4-8`, seat experiments=`claude-fable-5`. When a provider release re-points
any alias, the numbers do NOT carry: run the release-qualification protocol (champion cells
at k=2, then the min-max dials) BEFORE adopting or trusting. A release is a fresh min-max
opportunity, never a silent upgrade. **As of 2026-09-06 the `opus` alias no longer resolves
to G1. Every figure in the evidence files is therefore UNQUALIFIED until that protocol is
re-run.**

### §4.5 · Briefs (cache-shaped; pointers, not pastes)

Assemble ONE shared preamble, byte-identical across every spawn of the run (identical
prefixes are prompt-cache hits — the swarm pays for it once):

```
Repo root = your working directory. SPEC.md is the binding contract — READ the
sections named in your card FROM DISK; they are normative, never paraphrased here.
Global constraints: <the task's own rules: stdlib-only, no new files outside X, ...>
Self-check before reporting, with all scratch files OUTSIDE the repo (system temp).
Report EXACTLY:
STATUS: DONE | BLOCKED(<question>)
FILES: <touched>
CHECK: <command> -> <result, 1 line>
NOTES: <=3 lines
If any instruction cannot be applied exactly as written: STATUS: BLOCKED. Never guess.
```

Then a per-worker card: worker id · OWNED files (exact list — touch nothing else) · spec
sections BY REFERENCE · the byte-exact rules and trap warnings that bite (these are the only
pasted lines — error templates, orderings, "must NOT change" items) · upstream state
("fieldops/contracts.py is FINAL on disk — import it, never modify") · done-looks-like · the
self-check command to run.

**[LOCAL] Local cards carry MORE, not less** (an arena run failed 59/68 on locally written
sites with wrong call shapes). A local model has no slack for implied traps: every trap that
bites inside the card's OWNED files is pasted BYTE-EXACT — the full target signature, one
WORKED EXAMPLE per call-shape (before → after, verbatim from the spec), orderings, exclusion
list. Spec-by-reference is for API workers; a local card that says "see §2.5" has already
failed. After writing each local card, COUNT: every distinct call-shape in its owned files
appears as a worked example.

### §4.6 · Landing protocol (reports are claims)

After the WHOLE batch returns (all spawns of the dispatch message — never between spawns):
run `git status --porcelain` plus `git diff --name-only` — any changed file outside the
union of dispatched OWNED lists is reverted and the owner re-briefed. Spot-check each worker
with its own CHECK command or a 1-line import/run probe. A BLOCKED report gets an answer
(from spec/plan), then a fresh spawn, same lane. Never accept a green self-report as the
gate — in the arena a correct diff arrived under a wrong report, and only the script told
the truth.

### §4.7 · The gate (orchestrator-owned, deterministic)

Write your OWN gate script in the scratch dir — worked examples from the spec made
executable, one end-to-end integration path, the anti-regression traps ("must not change"
items verified verbatim), and the scope sweep. **Exit code decides.** Non-zero blocks: fix
via §4.8 and re-run. LLM review is optional and never substitutes.

**The gate is not answerable to the implementation.** A failing gate means the code is wrong
until you produce independent evidence that the CHECK ITSELF is malformed — the
implementation disagreeing with the gate is never that evidence. If the gate is genuinely
broken, or cannot observe the behavior the spec promises, stop and say so; do not weaken it
and declare a pass.

**[LOCAL] Two gate additions.** (a) The first stanza is an IMPORT SWEEP: load every file the
diff touched (`node -e "require('<file>')"`, `python -c "import <mod>"`, …) — a run with every
site correct still failed one node on a bad import. (b) For every distinct call-shape the spec
defines, the gate EXECUTES one worked example end-to-end and compares output verbatim — a
self-written gate that only inspected diff text passed shapes the hidden oracle failed. A
call-shape with no executable example is uncovered; say so in reconciliation.

### §4.8 · Escalation ladder (evidence travels, work doesn't restart)

**[LOCAL] Per failing LOCAL worker:** (1) on a TIMEOUT, lane-unavailable exit (code 2) or
partial return, first REVERT its partial diff, then re-run the card FRESH on the lane's API
fallback (`haiku` / `sonnet`) via `Agent` — never a verify-and-fix pass over partial local
work (haiku once patched over a timed-out 30B's partial diff, every self-check passed, and
the oracle failed exactly those sites); a clean failure with a report travels its diff plus
the gate evidence to that same fallback; (2) `opus`, same evidence; (3) `LADDER_EXHAUSTED`.
Escalations are expected accounting in this mode: reconciliation lists local-pass /
local-fail-API-caught / API-only counts. **Per failing API worker:** the rule below.

Per failing worker: (1) fresh spawn, SAME lane, with the gate failure plus the current diff
of its owned files pasted in; (2) one lane up (haiku→sonnet→opus), same evidence; (3)
`LADDER_EXHAUSTED` — you repair the minimal failing diff in-session and log it in
reconciliation. Hard cap: 3 attempts per worker, then stop and report to the human.

### §4.9 · The apply-tier (for the DIFFABLE portion only)

When the plan marks a node or cluster DIFFABLE:

1. **Compute, don't delegate.** The orchestrator reads the target files and the binding spec
   and emits one **SEARCH/REPLACE block per site**, in exactly this format:

   ```
   FILE: <path from repo root>
   <<<<<<< SEARCH
   <exact current line(s), copied VERBATIM from the file — byte-for-byte, same indent;
    include enough surrounding lines to be UNIQUE if a bare line repeats>
   =======
   <replacement line(s) per the spec rules>
   >>>>>>> REPLACE
   ```

   The SEARCH text MUST be verbatim from disk — that is the entire fidelity mechanism.
   Approximate SEARCH is a defect worse than no diff: measured, a worker handed a lossy
   "exact" patch scored BELOW the same worker reading the spec. Emit this as plan data to
   the scratch dir (`plan.blocks`), never narrated inline.

2. **Apply deterministically — no worker model.** Run an applier meeting this contract:

   - A block applies **iff** its SEARCH text is found **exactly once** in the current
     in-memory state of the file. Zero matches → `nomatch`. Two or more → `nonunique`.
   - Non-matching blocks are **NEVER** force-applied, fuzzed, or eyeballed into place.
   - Blocks for one file apply sequentially against the evolving in-memory text (a later
     block sees earlier blocks' results); the file is written once, at the end.
   - Line endings are preserved. Try an exact byte match first; count an EOL-normalized
     match separately so CRLF/LF drift stays visible rather than hidden.
   - Report `applied / nomatch / nonunique` counts and per-block residue.
   - Support an `--atomic` mode that refuses partial application (§4.9a needs it).

   A clean run is `applied == blocks, nomatch=0, nonunique=0`. This step costs ~0 tokens and
   ~0 seconds and is 100% reproducible.

   **Implementation.** If `tools/clean/apply_blocks.py` or
   `~/.claude/tools/clean/apply_blocks.py` exists, USE IT — do not re-implement. If neither
   exists, write a short stdlib script to the contract above in the SCRATCH dir, never in
   the repo. The contract is normative; the file path is a convenience.

3. **Residue → escalate, don't guess.** Any `nomatch` (your SEARCH wasn't verbatim) or
   `nonunique` (insufficient context) block does NOT get force-applied. Either re-emit that
   block yourself with more surrounding context, or hand the single block plus the file to
   one cheap worker: "apply this one edit." Deterministic-first; model only for the residue.
   **[LOCAL]** That cheap worker is a rig sequence when a current profile loaded (single block
   plus the file; residue workers batch in parallel within the §4.4 width), falling back to
   `haiku`. This is where the local
   model earns its keep under v5.0. A residue block touching auth, money, concurrency or a
   migration is not residue work — it is §6.

4. **Gate as always (§4.7).** The deterministic apply changes nothing about the gate — the
   script, not the block counts, decides done. A verbatim-clean apply is necessary, not
   sufficient: you can still compute a WRONG replacement (a planning miss), which only the
   gate catches.

### §4.9a · Fleet reuse (the scale multiplier)

Because the SEARCH/REPLACE set is data and the apply is deterministic, the SAME computed
diff applies to N repositories or instances at ~0 marginal cost. Compute once; apply
everywhere. The compute is spent on understanding ONCE, not re-litigated per target.

**A fleet needs its own policy, because per-target success does not imply fleet success.**
93 of 100 clean with 7 residue is not "93% done" — it is a fleet running two versions.
Declare the policy in plan.json before applying:

- `FLEET_POLICY: ATOMIC` — every target must apply clean or NONE are kept; any residue rolls
  the whole fleet back. **This is the default, and it is mandatory** for anything touching a
  shared contract, a wire format, auth, money, or a migration.
- `FLEET_POLICY: PARTIAL_ALLOWED` — clean targets are kept and residue targets are
  QUARANTINED: named explicitly in reconciliation, with the resume condition. Permitted only
  for independent, non-contract edits.

Print `FLEET: <policy> targets=<n> clean=<n> residue=<n> quarantined=<list|NONE>`. A fleet
run with unreported residue is a failed run.

## §5 · SOLO gate

Same as §4.7 — the script, not your eyes, decides done. Run it before declaring, and the
same "the gate is not answerable to the implementation" rule applies.

## §6 · Destructive interlock

DESTRUCTIVE = schema/data migrations, data deletion or movement, git history rewrites or
force-push, deploy/infra mutation, secret or auth-provider changes — anything irreversible
outside the working tree. Rules, regardless of path:

- never routed below `opus`; the worker returns PLAN plus exact commands plus diff plus
  rollback — it does not execute;
- you verify the rollback actually restores state before presenting;
- a live human approves execution. In auto-approve/headless mode the irreversible step is
  NOT executed: mark it `DEFERRED-DESTRUCTIVE` with the ready-to-run plan.

A computed diff touching auth, money, concurrency or migrations is STILL destructive. The
apply-tier does not launder it: it is presented as a plan with rollback and never
auto-applied.

## §7 · Reconcile and hand off

- **Requirement matrix:** every spec item → IMPLEMENTED / PARTIAL / DEFERRED / SCOPE-CREEP,
  with file refs.
- **Routing table:** planned vs ACTUAL spawns (worker · lane · model · attempts) plus any
  `LADDER_EXHAUSTED` or `DEFERRED-DESTRUCTIVE` events. Planned not equal to actual must be
  explained. DIFFABLE nodes carry `blocks applied / nomatch / nonunique` and any residue
  escalations.
- **Gate evidence:** the script's final output tail.

### §7.1 · Commit policy — ONE rule, stated once, nowhere else

The boundary is **publication**, not branch name:

| action | approval |
|---|---|
| local candidate commit (not pushed) | **none required**, unless §6 applies |
| push · PR · merge to a shared branch · release · deploy | **human approval, always** |
| auto-approve / headless mode | **no commits at all** — leave the tree uncommitted |

**Avoid towering commits.** Each node or DIFFABLE cluster lands as its own local candidate
commit — a rollback and attribution boundary, not publication — tagged
`[UNREVIEWED][<node>][<CLASS>] <summary>`. Do NOT accumulate a whole fan-out into one giant
working-tree diff; the plan's per-node data already gives you the boundaries, so commit along
them.

If any other section of this file appears to state a different commit rule, this table wins
and the other section is a defect — report it.

## §8 · Hygiene and optional add-ons

Cleanliness the core already enforces by construction: nothing non-product ever enters the
repo; every landing runs the scope sweep and reverts strays; SCOPE-CREEP is a named
reconciliation state. Beyond that, after the gate passes and before handoff, you MAY add
(interactively ask; pre-authorized runs note it in reconciliation):

- **Hygiene sweep (deterministic-first):** run the repo's own tooling when present (ruff /
  eslint / knip / vulture / tsc-unused ...) on the changed surface; what tooling can't see
  (orphaned files, dead branches, stale docs touched by this change) goes to ONE cheap
  worker scoped to THE DIFF ONLY — never a whole-repo crusade mid-task.
- **LLM review:** optional second read for hygiene, architecture, or requirement-fit — never
  the correctness gate (LLM reviewers hallucinate exactly where the deterministic gate
  doesn't).
- **Security — NOT optional:** any diff touching auth, sessions, input handling, or secrets
  gets a security read before handoff.

Commit behavior in this section is governed by §7.1. This section states no commit rule.

## §9 · The clean phase — WITHDRAWN 2026-08-05, pending real measurement

**This skill has no clean phase. Do not run one as part of a run.**

§9 shipped mandatory, was demoted to optional on 2026-07-31, and is now out entirely. The
one measurement it has is not evidence it works: on `arena_cleanup` at k=3 it cost +30% and
+34% wall for zero correctness gain — but every arm hit the 16/16 ceiling *including the arm
with no clean phase at all*, because that fixture's prompt asks for cleanup, so a plain arm
just does it by hand. The fixture left no headroom. So the honest state is **unmeasured**,
not measured-null, and an unmeasured phase does not ride along in the champion skill. If it
earns its keep on a fixture with headroom, it comes back with numbers attached.

Cleanup is still available — as a deliberate, separately-invoked `/orch-clean` when you have
a REASON (an untraced rename or signature migration, a run that removed or commented out
code, a repo with known half-migrated state). That is a decision you make, not a tax every
run pays. When you do invoke it, its ordering rule stands: **gate → clean → re-gate**,
because cleanup deletes code and the gate that ran before the deletion has verified nothing.

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

- **This file is complete.** No rule this skill enforces lives in a document you were not
  given. A cross-reference you cannot resolve is a defect to report, never a gap to fill by
  inference.
- Only top-level sessions hold the `Agent` tool — never expect a worker to fan out, never
  delegate orchestration itself.
- One writer per file per batch. Specs are read from disk by whoever implements.
- Worker reports are claims; the gate is the only evidence. A failing implementation never
  grants authority to demote the gate.
- Nothing non-product inside the repo, ever.
- Max 3 attempts per worker; the human is the fourth tier.
- The apply-tier is ONLY for DIFFABLE nodes; GENERATIVE work is never faked as a diff.
- SEARCH text is verbatim-from-disk or the block is invalid. Approximate diffs are banned.
- Deterministic apply never force-applies a non-unique or no-match block; residue escalates.
- The gate, not the apply counts, is the evidence. A clean apply of a wrong REPLACE is still
  a failure the gate must catch.
- The applier is ONE implementation used by §4.9 and by `/orch-clean`, specified by the §4.9
  contract. Re-implement it only when it is genuinely absent, and then in scratch.
- A fleet apply declares FLEET_POLICY before it runs; ATOMIC is the default.
- §7.1 is the only commit rule in this file.
- No clean phase runs as part of this skill (§9 withdrawn). Nothing unmeasured rides along
  in the champion; a phase re-enters only with numbers from a fixture that had headroom.
- **[LOCAL]** STEP ZERO runs first; a missing profile downgrades executors, never discipline.
- **[LOCAL]** No local model on the DIFFABLE critical path; CRITICAL and DESTRUCTIVE never run
  local; local dispatch is foreground and every worker returns before landing.
- **[LOCAL]** The rig batches 16 sequences over a ~333K-token KV pool, shared. Local workers run
  in PARALLEL within the printed `LOCAL-WIDTH`, sized by end-of-run context; a `429` halves the
  width and is never an escalation.
- The capability class is the architecture; the model alias is a mapping. Re-pointing an
  alias invalidates the numbers, not the algorithm.
- Report cost per SUCCESSFUL run, never per attempt. Per-attempt figures rank skills that
  fail half their runs as competitive; they are not.
- The dispatch log (§10) is mandatory, zeros included. Cards are FILES written before the spawn; `gate_exit` is a RUN field and nodes carry `node_check_exit`; a BLOCK without a `blocked_cause` charges the orchestrator's defects to workers. Logging failure is never run failure.
