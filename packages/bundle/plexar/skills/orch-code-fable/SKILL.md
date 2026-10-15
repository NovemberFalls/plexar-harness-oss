---
name: orch-code-fable
description: "Plexar orchestration skill /orch-code-fable: v5.1 (v5.0 apply-tier + the four things a live run showed it cannot see)"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-code-fable.md"
  source_sha256: "27c76dc90f3c42f5a9dd63ef210c07191950a84eeee4b36c66cba174392cff8c"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-code-fable — v5.1 (v5.0 apply-tier + the four things a live run showed it cannot see)

> ### §10 FIRES AT FIVE POINTS IN THE FLOW BELOW — NOT AT THE END WHERE IT IS WRITTEN
>
> `run_start` at **inventory** · `plan` at **plan freeze** · `dispatch` at **every spawn AND
> every SOLO node** · `outcome` when **each report lands** · `run` at **landing**.
>
> §10 is mandatory and it is the last section in this file purely for readability. **A run
> that reaches the inventory and writes nothing has already lost data that cannot be
> recovered afterwards** — the 2026-09-21 PDF-builder run did exactly that, because §1 said
> nothing about logging and §10 sat 420 lines later. **Read §10 before acting on §1.**


STATUS: **PROPOSED, derived from one measured run, not benched.** This is `/orch-code-anth`
v5.0 with four additions, every one of which is a defect that v5.0 let through on a real
task on 2026-09-05 (Grimhollow skill-tree evaluation and rebuild, browser-rpg). Nothing in
v5.0 is removed. Where v5.0 is silent this file speaks; where v5.0 speaks this file defers.
**Bench it against v5.0 on the arena fixtures before calling it live.** Until then, its
claim is narrower than v5.0's: *it would have caught these four, and v5.0 did not.*

Read `/orch-code-anth` first. This file assumes it.

Two facts from the published page (boord-its.com/skills, read 2026-09-05) that this version
leans on: the published `orchestrate v5.0` **refuses to run without its `apply_blocks.py`
applier** — this version keeps that, and extends the same refuse-don't-guess posture to
the generative assembler in §4.9b; and across 400 runs *"a plain checklist was the only
thing that helped"* while role-play personas showed no measurable effect — which is why
§4.5′ constrains worker output to a numbered checklist of sections and gives workers no
persona at all.

---

## §−1 · Restate the deliverable before the inventory (NEW)

v5.0 begins at "count the work." A run on 2026-09-05 counted the work perfectly, swarmed
correctly, gated correctly — and produced an **evaluation** when the owner had asked for a
**rebuild**. Every downstream step was right; the first step was missing.

Before §1, write one line and print it:

```
DELIVERABLE: <the artifact> · at <path or place> · consumed by <who> · which means <verb: fix / rebuild / report / decide>
```

Then apply one test: **if the ask names an outcome in the world and the DELIVERABLE line
says "report", stop.** A report is what you make *before* the outcome, not instead of it.
If the ask is genuinely ambiguous between the two, the report is the cheaper first step
— say so in the line, and say what the outcome step would be, so the owner can redirect
in one word rather than after a day.

## §0 · Apply-tier gate — unchanged from v5.0

## §1 · Inventory — v5.0, plus one row
**→ FIRST, before anything below: write the `run_start` row (§10).**


Add to the inventory: **`INSTRUMENTS: <each gate/check/ledger the run will trust> ·
reads <what file / what source>`.** Written down, not assumed — see §4.7a.

## §2 · Scale gate — unchanged from v5.0

## §3 · SOLO path — unchanged from v5.0

## §4 · SWARM path — v5.0 §4.1–§4.9 unchanged, with three additions

### §4.5′ · The brief is a file, and worker output has fixed sections (NEW)

v5.0 says briefs exist. It does not say what shape. Measured: a brief written **once as a
file** and read by N workers, with the worker's output constrained to **fixed, numbered
sections**, made the fan-in mechanical — the synthesis pulled "section 7" from nine files
with one `awk`, and a malformed output was visible as a missing section rather than as
prose that had to be read to be judged.

- The brief lives in the run's scratch or review directory. Workers are told to read it
  first and are given only the tree-specific delta in their prompt.
- The brief names the **output file path** and the **section list**. It says "write only
  this file" and "change nothing else."
- The brief says **no quota**: "if it is sound, say so and change little." Without that
  sentence, nine workers produce nine top-fives whether or not five exist.
- The brief says what the deterministic gates **already proved**, so no worker re-checks
  it. The worker's job is what a gate cannot see.
- **Keep a written table of worker → tree/partition before the first bounce**, and address
  a worker by that table, never from memory of a raw id. Measured: a one-node correction
  for Two-Handed was sent to the Elementalism author, who correctly refused to edit another
  tree; the collision was fixed from a third tree's side before it mattered, but only by
  luck. Nine opaque ids look alike; the table costs one line per worker.

### §4.9b · The generative-data tier (NEW — the apply-tier's sibling for GENERATIVE work)

v5.0's apply-tier makes DIFFABLE work deterministic. Measured: **GENERATIVE work becomes
nearly as safe when the worker emits DATA in a fixed format and a deterministic assembler
lands it.** Nine authors rewrote nine trees; none touched the shared file; a splicer
parsed each one's output, **refused** anything malformed (a missing slot, a mistitled
choice), and wrote nothing on refusal. Result: zero collisions, zero partial writes, and
every refusal was a real defect.

Rules, mirroring §4.9:

1. The worker's output is a **data file in a stated format**, never an edit to the
   shared artifact. The format is in the brief.
2. The assembler is **one implementation**, it **checks before it writes**, and it
   **refuses rather than force-applies**: a file that fails the check produces no write
   and a named reason.
3. **Escaping happens exactly once, in the assembler.** Workers write plain text. This is
   the same lesson as verbatim SEARCH: the fidelity mechanism is that nothing is
   transformed twice.
4. **Round-trip the assembler on existing data before its first real input.** Dump a
   known-good unit through the worker format, assemble it, and demand byte identity.
   Then break the format once and demand a refusal. An assembler that has never refused
   is untested.

### §4.7a · Instrument provenance and falsification (NEW — the largest addition)

v5.0 says "gate on a deterministic check, never on a model's opinion." Measured, that is
necessary and not sufficient. On 2026-09-05:

- **Three of four gates read the wrong file.** They hard-coded an absolute path to the
  original repository; run from a worktree they gated the original's copy and reported
  green for a file they never opened. Every gate passed. Nothing was checked.
- **Every prose instrument was wrong on its first run.** A regex ledger counted
  conditional riders and granted stats as held stats (dagger at 131 pp of crit against a
  40 pp cap — real figure 17). An absolutes check flagged 29 nodes; 24 were clauses whose
  job was to say the node was *not* absolute. A DR check stripped the half of the node
  where authors wrote the DR. An attribute list was copied from the trees it checked and
  so legitimised an attribute that did not exist.
- **A correct worker was nearly disbelieved** because a wrong counter disagreed with its
  report.

So, binding:

1. **Print provenance — for every instrument that reads AND every tool that writes.**
   Every gate prints the path it read, resolved, before its result; every assembler
   prints the path it wrote. A gate that cannot say what it read has not read anything.
   Both resolve their target **relative to their own location**, never by absolute path,
   or they are not portable across worktrees and the head-to-head is measuring one of
   them against nothing. *Measured the same day this rule was written:* the four gates
   were fixed and the assembler was not, so it reported `applied=4` while writing into
   the original repository — a folder the run was forbidden to touch — and the worktree
   under test never changed. The gates then read the unchanged file, reported the old
   defect, and were right. **The fix to one instrument is not the fix to the class.**
   When a path defect is found in one tool, grep every tool in the run for the same path.
2. **Falsify before trusting.** Break the thing the gate checks, once, and confirm red;
   restore and confirm green. A gate that has never failed is untested. This is in the
   repo's own doctrine and v5.0 does not say it; it belongs in the skill.
3. **Read the first hits before believing a count.** A prose instrument's first run
   reports a number. Read the first five to ten hits. If more than a third are the
   instrument's error, the count is not evidence yet — narrow the instrument, re-run,
   read again. Report the corrections *in the instrument's own file*, with the
   measurement, so the next run inherits the narrowing.
4. **Prefer silence to noise.** An instrument that cannot parse a shape stays silent on
   that shape and says so. A gate that cries wolf is ignored, and an ignored gate is
   worse than none because it produces false confidence.
5. **When a worker's report and a counter disagree, read the artifact, not the counter.**
   Twice in one run the worker was right.
6. **Write instruments from the authority, not from the thing checked.** A list of valid
   attributes comes from the stat system document, not from what the trees say they sell.

### §4.8′ · Fan-in consistency gates (NEW)

Parallel authors cannot see each other. Two defect classes only exist at the join, and
v5.0's landing protocol has no step for them:

- **Cross-worker uniqueness.** Names, identifiers, chip labels — anything that must be
  unique across the whole artifact and was chosen independently by N workers. Measured:
  three node-name collisions and five chip-name collisions across nine authors. The
  uniqueness gate runs at fan-in and covers every namespace, not only the obvious one.
- **Rename completeness.** A rename applied to a heading and not to the prose that
  refers to it. Measured: three renames fixed the node table and left the arithmetic
  section naming the old node; two independent auditors found it later. **A rename
  sweeps the whole file; the gate greps for the old name after.**

### §7 · Reconcile & hand off — v5.0, plus one section

The deliverable carries a section titled **"What this run got wrong"**: the
orchestrator's own defects, named with the measurement, so the next reader does not
inherit them. Measured: on 2026-09-05 the orchestrator's own rebuild introduced three of
the five defects one evaluator found, and its own earlier claim ("120 → 40 pp") was
withdrawn on an evaluator's correction. Both belong in the deliverable, not the transcript.

## §8 · Hygiene — v5.0, plus one hard rule

**A backslash never enters the shell tool inside code or content.** Not in a heredoc, not
in `python -c "..."`, not in a path. Measured: `\b` in `\browser-rpg` became a backspace
and the committed file read `Personalrowser` — the third time in one day, with the
warning already in memory. Forward slashes for paths; the Write and Edit tools for
anything else. The tell is `SyntaxWarning: invalid escape sequence` — treat it as a stop.

## §9 · Clean phase — withdrawn, as in v5.0

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

## Invariants — v5.0's, plus

- The DELIVERABLE line is printed before the inventory; a "report" against an
  outcome-shaped ask is a stop, not a plan.
- Every gate prints what it read. Every gate is falsified once. Every prose count is
  read before it is believed.
- Generative fan-out emits data; one assembler checks, refuses, and escapes exactly once.
- Fan-in runs uniqueness across every namespace and greps for every old name.
- The orchestrator's own errors are in the deliverable.
- **Unbenched.** These additions are derived from one run. Their cost is unmeasured.
  Report cost per SUCCESSFUL run when it is.

## What this version does not claim

It does not claim to be faster or cheaper than v5.0. §4.7a adds a falsification and a
read-the-hits loop to every instrument, and that costs turns; on a small, clean task it
may cost more than it saves. Its claim is that on the run it was derived from, v5.0
passed four classes of defect that this version's rules would have stopped, and one of
them (gates reading the wrong file) invalidated the entire baseline of a benchmark.
- The dispatch log (§10) is mandatory, zeros included. Cards are FILES written before the spawn; `gate_exit` is a RUN field and nodes carry `node_check_exit`; a BLOCK without a `blocked_cause` charges the orchestrator's defects to workers. Logging failure is never run failure.
