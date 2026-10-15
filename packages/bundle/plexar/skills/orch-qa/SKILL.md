---
name: orch-qa
description: "Plexar orchestration skill /orch-qa: the verify phase: two documents, one ledger, real regression"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-qa.md"
  source_sha256: "ffb921cf2ba76dab9f8be3b3d77f3a1153edd34fbaaa0ea1cbdd46152d0009cd"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-qa — the verify phase: two documents, one ledger, real regression

The third phase of `plan → code → qa`. Turns a milestone's completion into **two kept
documents plus a working set**, and keeps them honest over time:

| document | what it is | kept? |
|---|---|---|
| **`QA_PLAN.md`** | the **MASTER** — every test the project has, in a table, with what and how to test. **The registrar of pass/fail.** | kept, for backlogging |
| **`QA_PASSED.md`** | the **LEDGER** — every pass, when, by whom, against which build | kept, for reference on when things worked |
| `QA_ROUND.md` | the **working set** — only what is being tested now, in groups | a view; disposable |

The split is the point. A single file where passes are checked off loses *when* something
passed and against *what* — which is exactly the information you need to decide whether it
still holds after today's change. **A checkbox is not evidence. A dated, attributed,
build-stamped row is.**

**§3.5 adds a second split underneath this one — the CASE and the ISSUE — and at any size
past a couple of dozen items it is the load-bearing one.** Read it before writing
`QA_PLAN.md` for a project that will have a hundred tests.

---

## §0 · When this runs

- A milestone completed and the code phase alerted (`MILESTONE M<n> COMPLETE`).
- The human ran `/orch-qa` directly.
- A QA round came back from the human with FAIL/RETEST notes to process.

Do not run it mid-milestone. A half-built milestone produces QA items that fail for reasons
that are not defects, and those pollute the ledger.

## §0.5 · Verify the artifacts against each other — first, and again at the end

The three documents make claims about each other and nothing else checks that they agree.
Run it before you read anything and after you write anything:

```
python ~/.claude/tools/verify/verify_artifacts.py --root .
```

Windows/PowerShell: `python "$env:USERPROFILE\.claude\tools\verify\verify_artifacts.py" --root .`

It catches a plan node citing a QA ID that does not exist, a ledger row for an item that
was deleted rather than retired, an AUTO-recorded pass whose evidence carries no command
and exit code, a ledger row with no exercised paths (it can never expire, so regression
selection cannot see it), nodes sharing an accept command, and nodes with none at all.

**Exit 1 is a finding to fix, not a message to route around**, and fixing the artifacts is
part of the QA round. If the engine is not installed, say so — a skipped check that reports
nothing is indistinguishable from a clean one.

## §1 · Read before writing

1. **`PLAN.md`** — §7 backlog (what the milestone's nodes were), §8 QA obligations (the
   surface), the header's **QA authority** answer (which areas are AUTO vs OWNER), and
   **§3 Drift** — the decision log.
2. **`QA_PLAN.md`** and **`QA_PASSED.md`** if they exist. This skill is almost always
   updating, not creating.
3. The actual diff since the last QA round. `git log --oneline <last-qa-build>..HEAD` and
   the changed paths — regression selection (§4) is computed from this, not guessed.

**Decision check (from PLAN §3.2).** Compare what was built against the decision log. Any
built behavior that contradicts a logged decision is reported at the top of the QA round as
a **DRIFT** finding, before the test list. It is not a test failure — it is a divergence
between the plan and the thing, and it needs a human call: amend the decision, or change
the code. Silence here is how a project ends up somewhere nobody chose.

## §2 · `QA_PLAN.md` — the MASTER list, and the registrar of pass/fail

**Every test the project has, in one table, with instructions on what to test and how.**
This file is the authority: if the master says an item failed, it failed, whatever any
other document, console or agent says. Stable IDs that are never reused or renumbered —
`A.1`, `B.7`, letters by section, numbers within.

```markdown
# <Project> — QA Master
**Round:** 4 · **Milestone under test:** M2 · Session persistence
**Build under test:** 5ed1c9b (master) · **Generated:** 2026-08-05
**Authority:** backend AUTO (approved 2026-08-05) · frontend OWNER · migrations OWNER

| ID | Section | Test | Class | Auth | Status | Last result | Commit | What & how to test |
|----|---------|------|-------|------|--------|-------------|--------|--------------------|
| A.1 | Auth | Expired token is rejected with 401 | MACHINE | AUTO | PASS | 2026-08-05 | `5ed1c9b` | `pytest tests/test_session.py -k expired -q` |
| A.2 | Auth | Refresh rotates the token and invalidates the old one | MACHINE | AUTO | PENDING | — | — | `pytest tests/test_session.py -k rotate -q` |
| B.1 | Login screen | Wrong password shows an error that names the problem | HUMAN | OWNER | PENDING | — | — | Log in with a valid user + wrong password. Expect an inline error under the field, form stays filled, no page reload. |
| B.2 | Login screen | Session survives a browser restart | HUMAN | OWNER | RETEST | 2026-07-28 FAIL | `a3b52b4` | Log in, quit the browser entirely, reopen. Expect to still be signed in. Previously: cookie was session-scoped. Fixed in A2 (`5ed1c9b`). |
| C.4 | Migrations | Down-migration restores the prior schema | MACHINE | OWNER | BLOCKED | — | — | Needs a restorable snapshot fixture — see backlog F2. |
```

**Columns, and why each is there:**

- **Class** — `MACHINE` or `HUMAN`: *can a script decide this?* Intrinsic to the test.
- **Auth** — `AUTO` or `OWNER`: *did the human grant recording rights here?* Granted
  per-area in `PLAN.md`. Different axis from Class, and conflating them is how unverified
  work gets called verified.
- **Status** — the seven states below. **This cell is the project's answer** on whether the
  thing works.
- **Last result** — the date and outcome of the most recent verdict.
- **Commit** — **the build that verdict was taken against.** Without it a pass is a rumour:
  "A.1 passed" means nothing six weeks and forty commits later, and this column is what
  makes `git log <commit>..HEAD` a question you can actually ask.
- **What & how to test** — for MACHINE items, the exact command, runnable without
  interpretation. For HUMAN items, the steps and the expected result, written for someone
  who did not build it. *"Verify login works"* is not a test.

**Who tests what.** Backend belongs to the **AI and its agents** unless the human wants it.
**Frontend is uniquely the human's** — a machine cannot judge whether a screen makes sense
to a person. The `Authority` header line records that split, and the `Auth` column carries
it per item.

Rules that make the list usable:

- **An ID is permanent.** A retired test is struck through and marked RETIRED with a date
  and reason. It is never deleted and its number is never reissued — the ledger references
  it forever.
- **AUTO items carry the exact command.** Not a description of a command. The command, so
  it can be run without interpretation.
- **OWNER items carry steps and an expected result**, written for someone who did not build
  it. "Verify login works" is not a test.
- **A `RETEST` item carries what changed and why it should pass now** ("Previously: …
  Fixed in …"). Your existing plans already do this; it is the difference between a retest
  and a re-guess.
- **Status vocabulary** (seven states, existing `/qa-update` names kept): `PENDING` ·
  `PASS` · `FAIL` · `RETEST` · `BLOCKED` (cannot be tested — say what would unblock it) ·
  `REGRESSION-DUE` (previously passed, invalidated by §4 — carries the reason and the
  triggering diff) · `RETIRED`.

### §2.1 · `QA_ROUND.md` — the working set, so nobody is handed a hundred items

The master grows forever, and a list of two hundred items is a list nobody starts. Each
round writes a **working set: only what is being tested now, in groups.**

```markdown
# <Project> — To be QA'd · round 4 · build 5ed1c9b
Generated from QA_PLAN.md on 2026-08-05. **This file is a VIEW, not a source of truth** —
verdicts are recorded in QA_PLAN.md. Safe to delete after the round.

## Group 1 — Auth (MACHINE · AUTO · agent runs these)      2 items
## Group 2 — Login screen (HUMAN · OWNER · you run these)   3 items
## Group 3 — Regression, selected by §4                     4 items
```

Three rules keep it a view rather than a third source of truth:

- **Verdicts live in the master.** The working set is generated *from* it and never
  overrides it. If the two disagree, the master is right and the view is stale.
- **Grouped by who runs them**, agent work and human work separated, so the human's list is
  only ever the part a human must actually do.
- **It is disposable.** Delete it after the round; the master and the ledger are what get
  kept. A round sheet that accumulates history is just a worse master.

## §3 · `QA_PASSED.md` — the ledger

Append-only. A row is added when a test passes; rows are never edited, never removed. If a
previously-passing test fails later, that is a **new row in `QA_PLAN.md`**, not an edit
here — the historical pass really did happen, and erasing it destroys the record of when
the behavior broke.

```markdown
# <Project> — QA Passed Ledger
Append-only. A pass is a fact with a date attached, not a checkbox.

| ID | Test | Class | Auth | Passed | By | Build | Exercises | Evidence |
|----|------|-------|------|--------|----|-------|-----------|----------|
| A.1 | expired token rejected | MACHINE | AUTO | 2026-08-05 | orch-qa | 5ed1c9b | `auth/session.py` `auth/tokens.py` | `pytest -k expired` → exit 0, 4 passed |
| B.2 | session survives restart | HUMAN | OWNER | 2026-08-05 | owner | 5ed1c9b | `web/session/` (module) | owner verdict, Chrome 141 |
| A.1 | expired token rejected | MACHINE | AUTO | 2026-08-12 | orch-qa | a3b52b4 | `auth/session.py` `auth/tokens.py` | regression round 5, exit 0 |
```

- **Class** (`MACHINE` / `HUMAN`) is intrinsic: can a script decide it? **Auth**
  (`AUTO` / `OWNER`) is granted by the human per area at plan time. They are different
  axes and both are recorded. A MACHINE item in an area where auto-recording was not
  granted runs free in the gate but still needs an owner signature — common on migrations,
  where the check is mechanical and the trust is not.
- **Exercises** is the set of paths this item's test actually touches, and it is
  **mandatory at write time** — it is what makes the pass able to invalidate itself (§4).
  A row without it is unschedulable, which makes it a comment rather than a record.
- **Evidence** must contain a **command and an exit code** for anything auto-recorded.
  That requirement is structural, not stylistic: an agent cannot produce that shape for a
  test nobody ran without writing a command that was never executed — a lie, reviewable as
  one, rather than an ambiguity. For OWNER rows it is the human's verdict plus whatever
  environment mattered.
- **Redact by default.** Store the command, exit code, and counts — never raw output. This
  file is committed and grows forever; raw stdout eventually captures a token, a connection
  string, or a customer record.
- **The same ID appears many times.** Each regression round that re-passes it appends a
  row. That repetition is the value: `A.1` last verified 6 weeks and 40 commits ago is a
  different risk from `A.1` verified this morning, and only the ledger can tell you which.

## §3.5 · The CASE and the ISSUE are different records

*Generalised 2026-09-22 from `browser-rpg/qa/`, which is the only QA library in the estate
that survived past a hundred items and several reopenings. This section is the part of it
that does not depend on that repo's tooling. Plexar-Agents M3 (`PLAN.md` D1n–D6n) turns it
into code; until then it is prose, and prose is advisory — see the note at the end.*

A **CASE** is a reusable procedure: steps, expectations, the fixture it needs. It has no
verdict and never has one. An **ISSUE** is a defect's lifecycle and history. **A PASS,
FAIL, BLOCKED or NOT RUN belongs to a dated case result inside a run — never to the issue's
status.** Conflating them is what destroys history on a reopen: if the verdict lives on the
issue, reopening overwrites the record of when the thing last worked.

**Three axes, and they are not the same question:**

| axis | values | asks |
|---|---|---|
| `status` | `null` · In Progress · Completed · Rejected | where the defect stands |
| `queue` | backlog · fix · owner-review · closed | who is holding it right now |
| `readiness` | ready · not-ready · accepted | can an owner retest it today |

**`status: null` means UNSELECTED, not unknown.** A deferred or blocked item records its
reason and goes to `null` / backlog / not-ready — which pauses selection *without erasing
history*. A boolean cannot express that, and a project without it quietly loses the
distinction between "we decided not to test this yet" and "nobody has looked."

`Rejected` is a terminal state and it carries an **owner, a date and a reason**. A defect
someone decided not to fix is a decision, and a QA library that can only record fixes
cannot show you the decisions.

**Scoped acceptance is recorded as scoped.** An owner confirming "damage is landing and
approach distance is good" has not certified every escape, cancellation and defence edge
case. Record what was accepted and say plainly what it does not cover; a narrow acceptance
written down as a broad one is how a suite reports coverage it does not have.

**Generated views, one hand-edited page.** Master, backlog, completed and rejected lists are
**derived** from the stable records and regenerated. Exactly one file is hand-edited — the
owner's current worksheet — and **tooling never overwrites it**. A human editing a
generated view loses their work at the next build; a tool editing the human's page loses
the human's.

**Evidence is durable or it is declared missing.** Record path, timestamp and hash. Keep
links relative to the run. When an evidence file has moved, resolve it through a relocation
map rather than rewriting history. **When it is gone, mark durable evidence MISSING — never
leave a path that implies preservation.** A dead link that looks alive is worse than an
honest gap, for the same reason a hash that silently fails to verify is worse than no hash.

**Reopening preserves everything.** Earlier failures and earlier acceptances both stay. A
recurring case appearing in a new regression run does **not** reopen its linked issue unless
a failure is actually observed.

> **This section is advisory and it should not stay that way.** Every rule here is a
> sentence a tired session can skip, which is the exact disease `plexar-agents` exists to
> cure. M3's `qa build` / `qa check` make the generated views deterministic and make §5.5
> fail an exit code instead of a conscience. Until those land, this is discipline, not
> enforcement, and it should be read as the weaker thing it is.

## §4 · Regression — testing more than what changed

**The default is wrong in both directions.** Re-running everything every round is slow
enough that it stops happening. Re-running only what changed misses precisely the failures
worth catching — the ones where a change broke something nobody thought was related.

**The ledger is the mechanism, not just the record.** A pass expires by itself, because
each row pins the paths it exercises. Compare the round's changed paths against those, and
the regression set falls out as **data** — the same move the apply-tier makes for diffs:
the orchestrator understands the change and emits it, rather than delegating the judgment
to a model deciding how paranoid to feel today. An expired item returns to `QA_PLAN.md` as
**`REGRESSION-DUE`**, carrying the reason and the triggering diff.

Three invalidation triggers, each matched to what it protects:

1. **Path-touch → MACHINE items.** Precision where retesting is free.
2. **Module-level → HUMAN items.** Caution where retesting costs a person's afternoon;
   over-testing a human is expensive, under-testing them is worse.
3. **Contract-level → anything CRITICAL.** If the change touches something the plan marked
   CRITICAL (auth, money, concurrency, migrations, a shared contract), **every** item
   touching that contract expires regardless of path or module distance. Path-touch
   under-tests exactly the indirect coupling that is most expensive to miss, and the plan
   already knows which nodes those are.

Then add, on top of the computed set:

4. **Previously-broken** — anything that has ever moved PASS → FAIL. A test that broke once
   is the best predictor of a test that will break again. Cheap; always include it.
5. **Environment-changed** — if the fixture, test account, container image, or seed data
   moved, MACHINE passes taken against the old one are not evidence about the new one.

Print the selection and its reasoning before running anything:

```
REGRESSION: path=6 module=11 contract=4 prev-broken=2 env=0 → 23 of 61 items
  skipped 38: no pinned path intersects the changed set
```

**Say what you skipped and why.** A regression run that silently covers a third of the
suite reads exactly like one that covered all of it — the same silent-success failure mode
the whole toolchain is built against. If you cap the set for cost, say so in that line.

## §5 · Running the round

1. **AUTO items** (in areas where authority was granted in `PLAN.md`): run the command,
   capture exit code and output, promote to the ledger on success with real evidence.
   A non-zero exit is a `FAIL` with the output attached — never a retry-until-green.
2. **OWNER items**: leave them for the human. Present them as a clean checklist with steps
   and expected results, and **do not mark them anything**. An unmarked OWNER item is
   honest; a guessed one corrupts the ledger.

   **They never block the build.** Outstanding OWNER items are carried as **QA debt** and
   the next milestone proceeds — human availability is not the throughput limit. The price
   of that is stated every round: report the debt with its **age in milestones**, oldest
   first, so it cannot quietly accumulate. Debt older than three milestones is called out
   explicitly as a finding, not a line item; at that depth a defect has several layers of
   new code sitting on top of it.
3. **BLOCKED items**: say precisely what would unblock them (a fixture, a test account, a
   debug key) and, if it is cheap and non-destructive, build that unblocker as a backlog
   item rather than leaving the test permanently untestable.
4. **Never** mark an item passed on the basis of a model's reading of the code. The whole
   toolchain gates on deterministic checks and human verdicts; QA is not the place to
   start trusting an opinion.

### §5.5 · NOT RUN is not a verdict, and it blocks a coverage claim

**A required case that is failing, blocked, or unrun prevents a full-coverage checkpoint
claim.** Not "is noted alongside one" — prevents it. `NOT RUN` is the state a case is
created in; it is not a result, and it must never be counted toward green.

This is `node_check_exit: null is not 0` (`/orch-code-anth` §10), arrived at independently
in a different repo by a different route, which is the strongest kind of evidence a rule
gets. The two failures it prevents are the same failure:

- a round that covered a third of the suite **reads exactly like** one that covered all of
  it, unless the unrun items are named
- a checkpoint claimed over unrun cases is a green light nobody earned, and the next
  milestone lands on top of it

So the round summary carries them explicitly, and a coverage claim is refused while any
required case is not `PASS`:

```
COVERAGE: REFUSED — 3 required cases are not PASS
  QA-004 NOT RUN (created this round, never executed)
  QA-011 BLOCKED (needs a debug fixture — backlog node filed)
  B.7    FAIL    (backlog node filed)
```

Say `REFUSED` in those words. A summary that reports the numbers and lets the reader infer
the verdict is how the inference gets made optimistically at 1am.

## §6 · Processing results back

When the human returns `QA_PLAN.md` with verdicts written in. `/qa-update` is the named
entry point for exactly this and is now a shim onto this section — it carries no separate
behaviour, because when it did, it hot-fixed FAILs outside the backlog and ended in an
unapproved production deploy:

- **PASS** → append a ledger row with the date, tier `OWNER`, and the build.
- **FAIL** → keep it open, root-cause it, and file the fix as a **backlog node** in
  `PLAN.md` so it flows through the normal code phase. Convert the item to `RETEST` with
  what changed. Do not hot-fix around the backlog; that is how the plan and the code
  diverge.
- **Cosmetic / feedback** → a backlog node, not a QA failure. Keep the two separated or the
  pass rate stops meaning anything.
- **New behavior discovered while testing** → a new QA item with a new ID, and probably a
  new decision row if it contradicts the plan.

Print at the end:

```
QA: round=<n> milestone=<M> machine=<pass>/<run> owner-pending=<n> fail=<n> blocked=<n>
    regression=<selected>/<total> drift=<n vs decision log> debt=<n> oldest=<milestones>
```

## Invariants

- Two documents are KEPT: the master (current state, and the registrar of pass/fail) and
  the ledger (history). Never merge them. The round sheet is a view onto the master and is
  thrown away.
- **The master is the ultimate registrar.** A verdict anywhere else — a round sheet, a
  console, an agent's summary — is a claim until it lands in the master table.
- Every master row carries the **commit** its last verdict was taken against. A pass with
  no build attached cannot be aged, and an un-ageable pass is a rumour.
- Backend is the agent's to test unless the human wants it; **frontend is the human's**.
- The ledger is append-only. A later failure is a new row in the plan, never an edit here.
- Every ledger row carries date, tier, build, and real evidence. "Passed" is not evidence.
- IDs are permanent. Retire, never delete; never reissue a number.
- **A CASE is a reusable procedure and holds no verdict; an ISSUE is a lifecycle. A PASS,
  FAIL, BLOCKED or NOT RUN belongs to a dated case result inside a run, never to an
  issue's status** — that separation is what survives a reopen.
- `status: null` means UNSELECTED, not unknown. Deferring records its reason and pauses
  selection without erasing history.
- `Rejected` is terminal and carries owner, date and reason. A defect someone decided not
  to fix is a decision worth keeping.
- Acceptance is recorded at the scope it was given. A narrow acceptance written down as a
  broad one manufactures coverage.
- Master/backlog/completed/rejected are GENERATED. Exactly one page is hand-edited — the
  owner's worksheet — and tooling never overwrites it.
- Evidence carries path, timestamp and hash; a moved file resolves through a relocation
  map; a lost one is marked MISSING rather than left as a path that implies preservation.
- **A required case that is failing, blocked or unrun REFUSES a full-coverage claim**, in
  those words. NOT RUN is a creation state, never a result.
- AUTO status requires authority granted per-area in `PLAN.md`, and requires a command with
  an exit code. Everything else is OWNER, and OWNER items are never marked by an agent.
- Regression is selected by computed blast radius, and what was skipped is printed.
- Drift against the decision log is reported before the test results, not buried in them.
- FAILs become backlog nodes and flow through the code phase like any other work.
- **QA never ships.** No skill on this path pushes, deploys, or releases as a step in its
  own tail. Recording a verdict and acting on it are different decisions, and an unattended
  skill cannot obtain the approval the second one requires.
