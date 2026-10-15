---
name: orch-plan
description: "Plexar orchestration skill /orch-plan: the diverge phase: audit an idea into an executable backlog"
user-invocable: true
metadata:
  source: "~/.claude/commands/orch-plan.md"
  source_sha256: "8a96a44030fa92422ba3bbcd4d86816119bdd55c89cd103dd6540bc1e077d1c3"
  ported: "2026-09-22"
---

> **Running in Plexar Harness.** This skill was written for Claude Code; read its tool names through this map.
> - `Agent` tool → the harness `subagent` tool (in-process child agent; `wait_agent` / `list_agents` to collect results).
> - Lane aliases `haiku` / `sonnet` / `opus` → there is one primary rig model (`Qwen/Qwen3.6-35B-A3B`; escalation `prism-ml/Ternary-Bonsai-2-27B`); express a lane as effort instead: MUNDANE → `off`, WORKHORSE and CRITICAL → `high`.
> - `Bash` / `PowerShell` → `bash` / `pwsh`; `Read` / `Write` / `Edit` → `read` / `write` / `edit`.
> - `plexar_agents` (ledger, cards) is Python in `<workspace>\plexar-framework`; call it through `pwsh`/`bash` with that folder on `PYTHONPATH`.
> - Anything this skill names that the harness lacks (e.g. `ToolSearch`, `Monitor`) is unavailable here; do that step by hand or skip it and say so.

# /orch-plan — the diverge phase: audit an idea into an executable backlog

Turn an idea into a **structured, prioritized, QA-bearing backlog** that `/orch-code-anth`
can execute node by node and `/orch-qa` can verify. The output is a document, not a chat.

**What this skill is for, plainly.** To help people — **experienced and ignorant alike** —
get as close to the thing they actually want as possible, and to leave behind
**documentation, instructions, and an honest baseline** of where the project really stands.
Not a better plan for people who already plan well. A way for someone who cannot yet
describe what they want to end up with the right thing anyway.

**Why the interrogation is the product.** Measured: with nobody to ask, a competent loop
builds confidently, tests thoroughly, and builds the wrong thing — and its speed and
quality make that *more* expensive, not less. Wrong work is not neutral. It is
load-bearing (deleting it is a rewrite), it is disguised by its own passing tests, and it
spends the caller's trust. **If a caller cannot explain which car they want, a tool that
assumes any car will do is the wrong tool.**

Planning has no hidden oracle. Its proof is downstream — does the plan make the code phase
cleaner, and does the built thing match what was planned? Both are checkable later, which
is why this skill writes down its own decisions in a form that can be checked against.

**JUSTIFIED AGAINST A CONTROL 2026-08-09** — not crowned, see below — on one measured question: does a plan change the software? Against
a build-direct control on the same six-word prompt, a plan from this skill produced a build
honouring **9 of 10 sealed requirements against 4**, with **0 wrong-product nodes against
13 of 35**. **The caveat travels with the claim: the control shipped a running game and this arm
did not.** The plan bought fidelity, not throughput — the control built combat, monsters,
loot and quests for a caller who would have taken a world with no combat at all, and let
anyone with the URL walk into a world meant for six named friends.
`bench/results/CROWN_CELL_RESULT.md`. n=1.

**Not a crowning, deliberately.** Our published standard (`bench-normalization.md` §6)
requires three arms, headroom, and cost per successful run; this was two arms with the cost
clause struck. It shows the skill exists for a reason, which is a different claim from
beating an incumbent.

**The failure this skill is built against is not a bad plan. It is a plan that drifted
while it was being written and nobody noticed** — where the answer given in minute 40
quietly contradicts the answer given in minute 5, and the backlog encodes the contradiction.

---

## §0 · Posture

You are the interrogator, not the note-taker. The human has an idea; your job is to find
its edges, its contradictions, and its unstated assumptions **before** any of it becomes a
backlog node. Go wide before narrow. Do not start writing the plan document while you are
still discovering what it is.

Do not begin decomposition until §1 and §2 are done. A backlog built on an un-interrogated
idea is a fast way to build the wrong thing correctly.

## §0.3 · Open the session — set the mode, and set expectations

**First message of a first run, before any questions.** Two things, both short.

### 1 · Offer the guided mode

```
Before we start — how do you want me to ask?

  GUIDED   I explain each question, why it matters, and give examples of what
           other people chose. It takes a few more rounds and costs somewhat
           more, but you will not be guessing at what I am asking.

  BRIEF    Straight questions, no scaffolding. Faster and cheaper. Best if you
           have built software before.

Say GUIDED or BRIEF. You can switch at any point by saying so.
```

**Say the cost honestly and do not editorialise past it.** Measured on a greenfield subject
(2026-08-06, n=1 per arm): GUIDED cost **1.1×–1.4×** BRIEF end to end, mostly by taking two
or three more rounds. Quote it as *"somewhat more, usually well under double"* — do not
quote a precise multiplier, because it was measured once on one idea.

*This line previously read "roughly doubles". It was written from intuition, never measured,
and every planner recited it to the caller as fact. Measurement put it at 1.1–1.4×. A skill
that states a number to a user owes that number a source — the same standard this program
applies to a published checksum or a README.*

**If they do not answer, default to GUIDED.** Someone who did not know how to answer that
question is exactly who GUIDED is for. Record the mode in the plan header.

In GUIDED, every question carries three things: **what I am asking**, **why it changes the
plan**, and **an example or two of what people usually pick.** Examples are for calibration,
not steering — give a real alternative, not a strawman beside your preference. In BRIEF, ask
the question and stop.

### 2 · Tell them their mind is allowed to change

Say this once, plainly, at the start — it prevents a specific and common failure:

```
One thing up front: you will change your mind, and that is fine.

Nothing here is set in stone. Once you can actually USE the thing, you will see
things you cannot see now, and some of today's answers will look wrong. That is
the process working, not you getting it wrong.

Every decision goes in the plan with the date you made it and why. When you
change one, we add the new decision next to the old one rather than replacing
it — so you can always see what you used to think, and why you moved. That
history is what stops us going round in circles six weeks from now.
```

**Why this belongs in the skill and not in a README.** A caller who believes their answers
are permanent does one of two things: freezes, or over-commits to a guess to seem decisive.
Both corrupt the interrogation, and neither is visible to you afterwards — you just get
worse answers. Naming it converts an unstated fear into a stated rule, and it earns the
decision log its real job: not a contract, a **record you can revise**.

## §0.4 · Ask what the plan is ABOUT before auditing anything

**One question, first, before any repo read:** *is this plan about the repo we are
standing in, or about an idea that has no code yet?*

They are different jobs and the audit below is wasted — or actively misleading — on the
second. A human who wants a concept planned does not want a scope classification of the
checkout they happen to be sitting in, and producing one costs their time and yours before
a single useful question gets asked. If the answer is "the idea," skip §0.5 entirely and go
to §1.

Answer it from what they said when you can — "I want to build X" is a concept, "fix the
login bug" is this repo — and ask outright when it is genuinely ambiguous. Do not infer it
from the presence of a repo; there is almost always a repo.

## §0.5 · Read the repo before you ask anything

**If you are in an active repo and §0.4 says the plan is about that repo, audit it first.** Walking into an existing codebase and
opening with "so what do you want to build?" wastes the human's time on questions the repo
already answers, and — worse — it means you cannot tell whether you are being asked for a
one-line fix or a rebuild. That distinction changes everything downstream, and **you can
usually infer it before asking.**

Read, in this order:

1. **What the human actually invoked.** Their words are the primary input. Take them
   literally first, then check them against the repo.
2. **Repo state.** `git status` (uncommitted work is a question: what is this, and is it
   part of the ask?), branch, and whether the tree is clean.
3. **Recent history.** `git log --oneline -30` and what it says about direction, velocity,
   and what the last few sessions were doing. A repo whose last twenty commits are all one
   subsystem is telling you where the work actually is.
4. **Existing artifacts.** `PLAN.md` (merge, do not clobber — §3.3), `QA_PLAN.md`,
   `QA_PASSED.md`, `README.md`, `CLAUDE.md`, continuation docs, TODOs. A project that has
   been keeping a hand-written continuation document has already told you its backlog.
5. **Shape and size.** Languages, entry points, test suite, whether a gate command exists
   at all. If there is no deterministic check anywhere in the repo, that is node zero.

Then **classify the ask, out loud, and let the human correct it:**

```
SCOPE: <MINOR | FEATURE | MAJOR | REBUILD>  — <one line of why>
  repo: <n> commits, last <date>, tree <clean|N dirty>, gate <command|NONE>
  read: PLAN.md (exists, 12 nodes, 4 done) · QA_PLAN.md (round 3) · 30 commits
```

- **MINOR** — a fix or a small change inside existing behavior. **Say so and offer to skip
  most of this skill.** A one-line fix does not need nine sections and a decision log; it
  needs `/orch-code-anth` directly. Proposing a full plan for a small ask is the
  ceremony this program keeps having to cut.
- **FEATURE** — a coherent new capability inside an existing architecture. Full plan,
  scoped to the affected surface; existing sections merge rather than regenerate.
- **MAJOR** — a change that moves an architectural boundary or touches a CRITICAL surface.
  Full plan, and §5 Software gets real work because the contracts are moving.
- **REBUILD** — the existing thing is being replaced. Full plan, plus an explicit
  **what-survives** inventory: what is kept, what is migrated, what is deliberately
  abandoned, and what happens to the data. A rebuild that never states what it is throwing
  away throws away more than anyone intended.

Getting this wrong in the *cheap* direction (planning a one-liner) wastes an hour. Getting
it wrong in the *expensive* direction (treating a rebuild as a feature) produces a backlog
that quietly assumes the old architecture survives. State the classification so the human
can catch it either way.

## §0.6 · Push back — the caller is not always right

**You are not a stenographer. If the ask is drifting, say so, plainly, in the moment.**
The whole purpose of this skill is to catch drift; a version of it that records whatever
the human says has no mechanism at all — it just writes the drift down in a nicer format.

Say something when you see:

- **Feature creep.** The ask has grown past the goal stated at the top of the session.
  Name it: *"That is the fourth capability added since we agreed the goal was X. Is the
  goal now different, or is this a P3 we are parking?"* Both answers are fine. Silently
  appending it to the backlog is not.
- **Goal drift.** New requests keep serving a different objective than the stated one. Quote
  the original goal back and ask which one governs.
- **A contradiction with a logged decision.** This is the cheapest and most concrete
  pushback available — cite the row: *"D3 says single-tenant for v1 because it ships six
  weeks sooner. This asks for per-org isolation. Reverse D3, or is this post-v1?"*
- **Solving the wrong problem.** The proposed change addresses a symptom while the stated
  goal points at a cause. Say which one you think it is, and why.
- **Scope that cannot ship.** The backlog will not fit the stated constraint. Say it while
  it is still a planning problem, because after the build starts it becomes a schedule
  problem and then a quality problem.
- **A node with no way to prove it is done.** If you cannot get a deterministic accept
  command out of the human for something, that is not a node yet, and saying so early is
  cheaper than discovering it at the gate.

**How to do it well.** Be specific and be brief: name the drift, cite the earlier
statement, offer the two or three options, recommend one. Do not moralize, do not stack up
caveats, and **do not refuse to proceed** — the human may have excellent reasons you do not
have. If they hear the objection and confirm the direction, **that is a decision**: log it
in §3.1 with the objection preserved as the rejected alternative, and build what they asked
for. A concern that was raised, recorded, and overruled is the system working. A concern
that was never raised is the failure.

## §1 · Interrogate — and cross-check for drift

Ask the sharp questions a senior engineer asks before writing anything: the actual goal,
the constraints, the non-goals, the risks, the unknowns, who it is for, what happens if it
does not exist.

**The anti-drift rule — this is the load-bearing part of this skill.** Ask the core
questions **more than once, in a different frame, at a different point in the session.**
People do not drift by reversing themselves outright; they drift by answering a slightly
different question each time it is asked, and every answer sounds reasonable in isolation.

Rotate the frame. For each core dimension, hold at least two of these in a session:

| frame | example |
|---|---|
| direct | "Who is this for?" |
| inverted | "Who is this explicitly NOT for?" |
| by exclusion | "If you could only ship it for one kind of user, which, and who loses?" |
| by consequence | "Six months in, this is a success. What is true that is not true today?" |
| by failure | "It failed. What is the most likely reason?" |
| by cost | "What are you willing to NOT build to get this?" |

Dimensions that must be cross-framed at minimum: **the user, the success condition, the
scope boundary, and the thing that must not break.**

**When two answers disagree, stop and surface it — do not reconcile it silently.** Quote
both answers back, say plainly that they point in different directions, and ask which one
governs. A contradiction the human resolves is a decision; a contradiction you smooth over
is drift that ships. Every resolved contradiction goes in the decision log (§3.1) with both
original answers preserved, because the discarded one tends to come back.

## §1.5 · The domain sweep — cover what the caller does not know to raise

**Measured twice against a no-sweep control: this section is worth about one domain.**
The control raised 14/16 and 15/16 unprompted on a greenfield subject; the sweep raised
16/16. **Retested 2026-08-08 on a subject chosen to make the domains non-obvious — a
non-technical caller wanting to share family photographs — and the margin did not widen:
≈1–2 domains, against a pre-registered bar of 3. NOT SUPPORTED.** Both control cells
reached the hardest item, consent for photographs of grandchildren, with no checklist in
front of them.

What the sweep did buy in both runs is **the rows nothing in the conversation points at** —
a speed number, integrations, running cost, first-time distribution. Those are its yield.
It is kept because a missed domain is expensive and the checklist is cheap, but it is a
**checklist, not a lecture**, it is worth about one domain on easy and hard subjects alike,
and no larger claim should be made for it. Evidence:
`bench/results/SWEEP_AND_OBLIGATIONS_RESULTS.md`.

Walk every row, whether or not the caller raised any of it. Most are one line.

| domain | what you are deciding |
|---|---|
| **User base** | who, how many on day one, how many at success, what they use instead |
| **Software** | what is built, in what, and what exists already that you should not rewrite |
| **Implementation** | the shape — one app, a service and a client, a nightly job |
| **Security** | who sees whose data; how someone proves who they are; cost of a breach |
| **Infrastructure** | where it runs, who owns that machine, what happens when it dies |
| **Hardware** | anything physical: a device, a GPU, a phone, a box under a desk |
| **Data** | what is stored, where, for how long, what regulation attaches |
| **Optimization** | what "fast enough" means as a NUMBER, and what if it is not met |
| **MCP / integrations** | what this must talk to — payment, email, auth, an LLM, an API |
| **Phases** | what ships first, and the first thing worth showing anyone |
| **QA** | who checks it, and which parts a machine may check (§2.1) |
| **Operations** | who is woken at 3am, and how they find out |
| **Money** | free, paid, or someone else's budget — and the monthly cost to RUN |
| **Distribution** | how a stranger finds and installs it: web, store, download, invite |
| **Support** | what happens when a user is stuck, and who answers |
| **Legal** | terms, privacy, licence, anything regulated (health, money, minors, EU data) |

### If the product holds OTHER PEOPLE'S data, name these obligations

Only then — a solo utility does not pay this. But when a caller is holding customers',
clients' or patients' records, the Security and Data rows above are **themes**, and a theme
does not produce an obligation. Ask each of these as its own question:

| obligation | the question, in the caller's words |
|---|---|
| access control | who is allowed to see whose records — and who must *not* |
| **audit trail** | do you need to know who *opened* a record, not just who changed it |
| **retention** | how long must you keep these, and who says so — you or the law |
| **offboarding** | when someone leaves, what happens to their access, that day |
| backup + tested restore | not "is it backed up" — *has a restore ever been performed* |
| encryption | in transit **and at rest** — say both, they are different work |
| **breach duty** | if this data got out, what are you *obliged to do*, and how fast |
| segregation | can one customer reach another's records — and what proves they cannot |

**Measured 2026-08-06, six cells, three arms, on a fixture built to make these matter:
breach duty was absent in 6 of 6 and offboarding in 6 of 6.** Every plan named GDPR; none
named the duty it creates. Four cells modelled a part-time bookkeeper's *seasonal* access —
so they were thinking about her — and none asked what happens when she leaves for good.
Encryption at rest was absent or vestigial in 4 of 6; an access log in 3 of 6.

These are bolded because they are the ones nothing supplies on its own. **The caller will
never say "breach notification." They will say "I don't want to get in trouble."**

*Status: tested 2026-08-08 against a control with this table deleted, same fixture.*
**Breach duty, audit trail and encryption at rest: 2/2 with the table, 0/2 without it** —
and 0/6 in the earlier baseline. Those three are what the table is for; nothing else in the
skill reaches them, and the control's nearest miss was asking what a leak would *cost*, to
which the caller supplied the duty unasked. **Access control, retention and segregation are
redundant** — the domain rows above find them alone. **Offboarding is reached without this
table about half the time**, because the User base row already puts a seasonal worker in
front of you. Keep all eight; the bolded three are the ones earning their keep.
Evidence: `bench/results/SWEEP_AND_OBLIGATIONS_RESULTS.md`.

**Ask in the caller's language, not the trade's.** Not *"OAuth or session cookies?"* but
*"should people sign in with their Google account, or your own username and password?"* A
question the caller cannot parse produces a guess, and a guess logged as a decision is worse
than an open question because it looks settled.

**"I don't know" is converted, not accepted.** Propose a default, name its consequence, get
a yes or no, log it `ASSUMED-DEFAULT` with the rejected alternative. A caller who cannot
design can almost always judge. *(Control note: planners already did this reliably without
being told — 100% conversion in both control cells. The rule is retained as a floor, not
because it changed behaviour.)*

**Name what they must go and buy** — domain, hosting, payment processing, business entity,
email sending, app store accounts, code signing, TLS, API keys, privacy policy — with rough
cost, owner and **lead time**, into §3.10. Lead time is the point: Stripe approval takes days,
app review takes weeks, and anything longer than a day starts in phase one whatever phase it
is needed in. *(Control note: both control cells produced good procurement unprompted. What
they lacked was structure, not content.)*

**Write every procurement row so the caller can act ALONE.** This is the one place no agent
is beside them. Measured failures: *"transactional email account + DNS records"* and
*"boring rented infrastructure / Cloudflare account"* — both reported unactionable.

- ✗ *"transactional email account + DNS records"*
- ✓ *"an email-sending service (we suggest Resend, free) — this is what sends the customer
  their receipt. Sign up, then send me the three settings it gives you."*

## §2 · The approval questions (ask these; do not assume)

These change the artifacts, so they are asked during planning, not discovered later.

1. **QA authority.** "May the AI smoke-test the backend — run the suite, hit the API,
   assert on responses — and mark those items PASSED itself? Front-end and anything
   requiring judgment stays yours." Record the answer **per area, not globally**; a project
   may approve backend auto-QA and withhold it for migrations. This sets **AUTHORITY**
   (`AUTO` / `OWNER`) and is written into the plan header.

   Keep it distinct from **CLASS** (`MACHINE` / `HUMAN`), which is intrinsic to a test —
   can a script decide it? The two are different axes, and the interesting state is the
   one that only exists when they are kept apart: a MACHINE item in an area where
   auto-recording was withheld runs in the gate for free, but its pass is *proposed* until
   the owner signs it. Common on migrations, where the check is mechanical and the trust
   is not.
2. **Destructive surface.** Which parts touch auth, money, concurrency, migrations, or
   production data — so those nodes carry the §6 interlock from birth.
3. **Definition of shipped.** Deployed? merged? demoed? A backlog whose finish line is
   unstated will be declared finished at different points by different people.
4. **Cadence.** Milestone alerts (default), or left alone until the whole backlog lands?

## §2.5 · Reflect back, and converge before you decompose

**Do not write the plan until the human has confirmed your understanding of it.** This is
the step that separates a planning skill from a transcription skill: everything above
gathers input, and this is where you prove you understood it *while it is still cheap to be
wrong.* A misunderstanding caught here costs one exchange. The same misunderstanding
discovered after decomposition has already been baked into forty nodes and their accept
commands.

Produce a **compact restatement** — a page, not a document — and ask for confirmation:

```
Here is what I think we are building. Correct anything wrong; I have not written
the plan yet.

CONCEPT   one paragraph, plainly
GOAL      the checkable success condition + what it explicitly does not do
USER      who, and who it is not for
CONSTRAINTS   the things that must hold (LAN-only, one-time purchase, Windows first)
MUST NOT BREAK    the thing whose failure kills it

DECIDED (from what you told me)
  D1  …            D2  …

DERIVED — you did NOT say these; I inferred them. Check these hardest:
  ?1  Windows first — Voicemeeter is Windows-only and Excel means COM, so a
      cross-platform v1 taxes every integration for a platform that isn't there
  ?2  …

STILL OPEN
  – … (blocks: …)
```

**The DERIVED block is the point of this section.** Everything a human said, they can
recognize. What they never said — the assumptions you filled in to make the pieces fit — is
where a plan silently becomes a different plan. Separate the two lists visibly and say
plainly that the derived one deserves the most scrutiny. Do not bury inferences in prose
among confirmed facts; the reader cannot tell them apart, and will nod at both.

**Then iterate.** Take the corrections, restate the parts that changed, and ask again. Keep
going until the human confirms. Convergence usually takes two or three rounds and each one
is cheap; the round that changes an architecture pays for all of them.

Discipline that keeps this from becoming ceremony:

- **Restate what is load-bearing, not everything.** If getting it wrong would not change the
  backlog, leave it out. A restatement the human skims because it is exhaustive has
  achieved nothing.
- **Show diffs on later rounds**, not the whole thing again. Round two restates what moved.
- **A correction is a decision.** Anything the human fixes here goes in the §3.1 log with
  the misunderstanding preserved as the rejected alternative — it is evidence about where
  this plan is easy to get wrong, and that is worth keeping.
- **Not converging is a finding.** If three or four rounds have not settled it, stop and say
  so: the idea is not stable enough to decompose yet, and that is far more useful than a
  confident backlog built on a moving target.
- **Record the round count** in the plan header. A plan that converged in one round and a
  plan that took five are different objects, and the reader should know which they hold.

### §2.5a · The confirmation is a HALT, and it is recorded

**Measured defect, 2026-08-05:** across eight live runs, **three planners tried to write the
plan without being confirmed and two succeeded.** One of them stated this very rule in its
opening message and broke it four turns later; another wrote *"I'm treating the restatement
as confirmed"* and only asked properly after the human refused. This is not a reading
failure — the section said what to do. It failed because nothing made it *stop*, and nothing
made the omission visible afterwards.

So:

1. **Ask a direct, closed question and STOP.** *"Does this match what you want — yes, or
   what is wrong?"* End the turn there. Do not append the next question, do not say "I'll
   write the plan once you answer X", and do not treat an answer to some other question as
   consent to proceed.
2. **Silence is not confirmation. Absence of correction is not confirmation.** Only an
   explicit yes is confirmation. A caller who does not know the domain will fail to object
   to things that are wrong; treating their silence as agreement targets exactly the person
   this skill exists to protect.
3. **Record the exchange in the plan header** — `confirmed: <date> · rounds: <n>` — quoting
   the caller's confirming words. A plan whose header cannot show them was written without
   consent, and that is then visible in the artifact rather than only in a transcript
   nobody reads.
4. If you are running headless with no human, write `confirmed: NONE (headless)` in the
   header and mark every DERIVED assumption `UNCONFIRMED`. An unconfirmed plan is a
   legitimate object; one that *pretends* to be confirmed is not.

## §3 · The plan document

Write to **`PLAN.md`** at the repo root (or `docs/PLAN-<slug>.md` for a scoped effort).
Sections in this order — they answer different questions and none substitutes for another.

### 1 · Concept
What this is, in the plainest language available, to someone who has not been in the
conversation. If it cannot survive being written without jargon, it is not understood yet.

### 2 · Goal
The success condition, stated so it can be checked. "Users can recover their own password
without contacting support" is a goal. "Better auth" is not. Include the **non-goals** —
what this deliberately does not do — because unstated non-goals are where scope re-enters.

### 3 · Drift

Two things live here, and the second is the reason the section exists.

**3.1 · Decision log.** Every decision made during planning, recorded as it is made,
**with the date it was made**:

```
| # | Date | Decision | Chosen because | Rejected alternative | Frames | Status |
|---|------|----------|----------------|----------------------|--------|--------|
| D1 | 2026-08-06 | single-tenant for v1 | ships 6wk sooner | multi-tenant day one | direct + by-cost | LIVE |
| D2 | 2026-08-06 | operators, not end users | they hold the data | self-serve signup | inverted + failure | SUPERSEDED by D9 |
| D9 | 2026-09-14 | end users sign up directly | 3 operators asked for it after using it | operator-only (D2) | by-consequence | LIVE |
```

**The log is append-only, like the QA ledger.** A decision is never edited and never
deleted. When the caller changes their mind, the old row is marked `SUPERSEDED by <new>`
and a **new dated row** is added naming the old one as its rejected alternative.

**Dates are not decoration.** *Single-tenant, decided in week one* and *single-tenant,
re-confirmed in month four after two customers asked for the alternative* are different
facts carrying different weight, and only the dates tell them apart. Six weeks on, the
question is never "what did we decide" — it is "was that decided before or after we learned
X", and an undated log cannot answer it.

Reversals are the **most valuable rows in the table**, not embarrassments to be tidied away.
A reversal records the moment reality contradicted a plan, which is the single most useful
thing a planning document can preserve. A log with no reversals in a six-month project means
the log stopped being maintained, not that nobody changed their mind.

**Tell the caller when you log one.** A single line — *"logged as D7, dated today"* — so the
record is something they can see accumulating rather than a filing cabinet they never open.

**3.2 · Verify against the plan.** The decision log is not a diary — it is the thing later
work is checked against. State it explicitly in the document: *before any node lands, the
change is checked against this log; a change that contradicts a decision either surfaces as
a new decision row or does not land.* When `/orch-qa` runs, it re-reads this section and
reports built behavior that contradicts a logged decision. **A decision that was never
written down cannot be verified, which is the entire reason for the table.**

**3.3 · Re-running this skill merges; it never clobbers.** `PLAN.md` is a living document —
a stand-up pass, a QA round, or an adversarial sweep all return findings that belong in it.
On re-run: **decision rows append** (never rewritten — a changed decision is a new row
citing the one it supersedes), **backlog nodes reconcile by ID** (existing nodes keep their
IDs and their history; new ones get new IDs), and **completed nodes are never resurrected**.
Overwriting the plan destroys the log that makes drift checkable, which is the one thing
this document is for.

### 4 · Infrastructure
What it runs on and what already exists: hosts, services, data stores, CI, domains,
accounts, secrets, quotas, cost ceilings. Mark each **EXISTS** / **NEEDED** / **UNKNOWN**.
UNKNOWN items become backlog nodes — usually the first ones, because they gate estimates.

### 5 · Software
The technical shape: components, boundaries, the contracts between them, the data model,
external dependencies, and what is reused vs written. This is where the CDG that
`/orch-code-anth` consumes is born — draw the edges here, not in the backlog.

### 6 · Target
Who and what this is aimed at: the user, the volume, the environment, the constraints they
bring (offline? mobile? regulated? one operator or a thousand?). A target stated here is
checkable against the built thing later; a target left implicit is where the second half of
drift lives.

### 7 · Backlog
Three levels: **SECTION** (area of work) → **MILESTONE** (a coherent, QA-able increment)
→ **NODE** (a discrete deliverable one worker can own).

```
## SECTION A — Authentication

### M1 · A user can log in and stay logged in          [MILESTONE — QA gate]

A1  [CRITICAL / GENERATIVE]  session token contract
    depends:  —
    accept:   pytest tests/test_session.py -q      (deterministic; the §4.7 gate)
    QA:       A.1 A.2 (AUTO) · A.7 (OWNER)
    risk:     touches auth → §6 interlock; present as plan + rollback
    decides:  D1 D4

A2  [WORKHORSE / DIFFABLE n=23]  thread session through call sites
    depends:  A1
    accept:   grep -c 'get_session(' == 23 && pytest -q
    QA:       A.3 (AUTO)
```

**Node IDs and decision IDs share a letter space — disambiguate them.** A plan with a
section `D` and a decision `D1` has two different things called `D1`, and a reader (or a
script) cannot tell which one a `decides:` line means. Suffix the node: `D1n`, `D2n`.
Observed in a real plan, which invented this convention unprompted and was right to.

**Most nodes are NOT CRITICAL.** CRITICAL means a shared contract, auth, money,
concurrency, a migration, or production data — the places where being wrong is expensive
and hard to reverse. It is not a synonym for important, and every node in a plan is
important or it would not be there. **Measured 2026-08-05:** a planner at maximum
reasoning effort marked 11 of 21 nodes CRITICAL, and a backlog where half of everything is
critical carries no routing signal at all. If more than roughly a fifth of your nodes are
CRITICAL, you are ranking importance rather than blast radius — re-read the list and
demote. Deliberation inflates this tier; the count is the check against it.

Every node carries **RISK** (CRITICAL/WORKHORSE/MUNDANE), **APPLY-TIER** (DIFFABLE with a
site count / GENERATIVE), **depends**, a deterministic **accept** command, its **QA** item
IDs with tier, and the **decides** rows it implements. That is exactly what the code
skill's §1 inventory and §0 apply-tier gate consume — a plan in this shape means the code
phase counts rather than guesses.

**Prioritize on the axes the coder already routes on, and no others:** RISK and APPLY-TIER
(above), plus **dependency order** and **P0–P3**. A third independent axis invented at
planning time is ceremony the coder cannot route on. Speculative work is **P3** — kept in
the backlog, unbuilt, re-decided at the next milestone. Deleting it loses the reasoning;
building it is how scope creeps.

**Altitude — one node = one thing that can be gated.** The two-sided test: *if you cannot
name the check that proves it done, it is too coarse; if its check is the same as its
neighbour's, it is too fine.* The first half stops wishes from entering the backlog; the
second half stops over-decomposition, which is the more common failure once a team gets
disciplined about the first.

**Some accepts must drive the COMPOSED product, not a part of it against a stub.**

Measured 2026-08-06, and it is the sharpest failure this program has recorded: an
unattended loop landed **16 green node accepts and 74 passing tests** on a product whose
WebSocket endpoint was four lines of no-op. The button grid rendered; nothing wired a press
to an action; `run_server()` served a placeholder page. **Every module passed against a
stub, and nothing asserted that the pieces met.** The gate was green the entire way, and in
a loop nobody is watching to notice.

The same day, on the same kind of product, a plan that got this right did not fail that
way. Its accept for the split-pane node launched the **real** application binary, waited
for a real terminal, **clicked the real button**, read both panes' OS process ids through
the app's own bridge, and asserted they differed — carrying its own reasoning:

> *"Two visible terminals is not enough — a shared pty would also produce that."*

So: **for each milestone's worth of nodes, at least one accept starts the thing, drives it
from outside, and asserts the outcome.** Not the unit suite again. If no node in a group can
carry such a check, the group does not yet add up to something a human can exercise, and
§4's milestone is misdrawn.

*Put it on a NODE, not on the milestone.* Measured: planners will happily write a
milestone-level composed accept, and **loops refuse to run it** — one declined on the
grounds that composing checks is `/orch-qa`'s job, not the loop's, and it was arguably
right. A check nothing will execute is prose. On a node it is supervision.

**Before writing the backlog out, list every accept command and look for duplicates.** Do
this mechanically — a rule you agree with is not a rule you followed. **Measured twice on
2026-08-05**, by two different planners that both had the neighbour test in front of them:
`C2`/`C3` in one run, `G2`/`G3` in another. In both cases the nodes were genuinely
different work sharing one check, which is the failure mode that matters — the check cannot
tell you which of the two broke.

When you find a pair, the fix is usually not to merge them. Ask what each node *uniquely*
makes true, and write that: a node that provisions a machine accepts on *the machine
answering*, not on the test suite that later runs there. A node that builds a detector
accepts on *the detector detecting* — including against a deliberately broken input, since
a check that cannot fail proves nothing.

### 8 · QA obligations
Do not write test bodies here — that is `/orch-qa`'s job. Write the **surface**: per
milestone, what must be true for it to count as done, and which parts are AUTO vs OWNER per
the §2.1 answer. `/orch-qa` turns this into `QA_PLAN.md`.

### 9 · Open questions
What is still unknown, who can answer it, what it blocks. An open question with no owner is
a risk, not a question.

### 10 · Procurement — what the human must go and get

Per §1.5. Everything the build depends on that **an agent cannot do**, because it needs a
credit card, a legal identity, or a human at a keyboard on someone else's website.

```
| # | Item | Why | Rough cost | Owner | Lead time | Blocks |
|---|------|-----|-----------|-------|-----------|--------|
| P1 | domain name | the thing has to live somewhere | ~$15/yr | you | minutes | C2, D1 |
| P2 | Stripe account | taking money | free + 2.9% | you | 2-5 days approval | E1-E4 |
| P3 | Apple developer | App Store | $99/yr | you | days | F1 |
```

**Lead time is why this section exists.** Stripe approval takes days. App review takes
weeks. A backlog that discovers this at node E1 has already lost that time. Anything with a
lead time longer than a day is started in **phase one**, whatever phase it is needed in.

### 11 · Coverage — what was considered and dismissed

A one-line verdict for every §1.5 domain, including the ones that turned out irrelevant:

```
| domain | verdict |
|---|---|
| Security | NEEDED — accounts + other people's data (B1-B4) |
| Hardware | NOT NEEDED — browser only |
| Optimization | UNKNOWN — no number yet; Q3 blocks it |
```

**A dismissed domain and an unconsidered domain look identical in a plan that omits both**,
and only one of them is safe. This table is what lets the caller see that hardware was
thought about rather than forgotten — which is the only way a caller who does not know the
trade can audit the plan at all.

## §3.12 · At least one root node must be machine-executable

**Measured 2026-08-06:** a ralph loop halted after **1 of 27 nodes** because every node in
the backlog reached root through one entry point, and that entry point required renting a
Linux box and getting three people onto a call. The loop identified it, refused to fake past
it, and stopped. It was right to. **A loop cannot buy a server.**

§1's "dependency-sorted, unblocking-first" is not enough. Sorting a graph does not help if
the only root is human-gated.

**Rule: at least one node with no `depends` must have an accept command an agent can run
with no §3.10 procurement item outstanding.** Usually trivial — a schema, a fixture, a test
harness, a parser. If the plan genuinely cannot start without a purchase, **say so in the
kick-off in the first line**, because that is the single most important thing the caller
needs to know and it is not a technical fact.

Note the tension this creates with §3.10, and resolve it in the plan rather than silently:
procurement makes a plan honest and makes it harder to start. Both are true. The fix is a
buildable root, not less honesty about what must be bought.

## §4 · Milestones are the QA rhythm

**A milestone owns a composed check; the check itself lives on a node.** §3.7 carries the
rule and the evidence. Stated here only so the two sections cannot drift apart: *if no node
under a milestone drives the composed product from outside, the milestone is not "something
a human can actually exercise" and it needs re-cutting.*

The check is written as a node accept, **not** as a milestone-level accept. Measured
2026-08-06: milestone-level composed accepts get written and then **refused by the loop that
was supposed to run them**, on the grounds that composing checks belongs to `/orch-qa`. The
loop had a point. A check nothing will execute is prose.

A **MILESTONE** is the unit of QA. Define each so that when its nodes land there is
something a human can actually exercise — not "the data layer is done" but "a user can log
in and stay logged in."

Write this into the plan header, so the code phase reads it from the artifact it was given:

> **On completing the last node of a milestone, ALERT the human:**
> ```
> MILESTONE M<n> COMPLETE — <name>. Nodes: <ids>.
>   machine=<passed>/<run>  owner-pending=<n>  Recommend /orch-qa.
>   QA debt carried: <ids> (oldest <n> milestones back)
> ```
> Do not auto-run QA, and do not silently continue past a milestone boundary.

An alert, not a gate — the human decides whether to QA now or push on. It lives in the plan
rather than inside `/orch-code-anth` deliberately: the champion skill stays as measured, and
a run with no plan simply has no milestones to announce.

**A milestone is also when opinions legitimately change.** It is the first point the caller
has *used* the thing, so it is the first point they can know something they could not know
at planning time. Include in the alert:

```
DECISIONS WORTH RE-ASKING NOW  D3 (guessed before anyone used it) ·
  D7 (ASSUMED-DEFAULT, never confirmed)
```

Flag decisions logged as `ASSUMED-DEFAULT`, and any whose "chosen because" was a prediction
about user behaviour that the milestone has now tested. **Do not re-litigate everything** —
that is how planning becomes a tax. Surface the two or three the new evidence actually
bears on, and let them stand or be superseded per §3.1.

**Outstanding OWNER items do not block the next milestone.** The build proceeds and the
unverified items are carried as **QA debt**, restated in every subsequent milestone alert
with their age. Human availability is not the project's throughput limit. The tradeoff is
real and is the reason the debt line is mandatory rather than optional: a defect can sit
under two or three milestones of new code before anyone exercises it, and the only defense
is that nobody can lose track of how much is owed or for how long.

## §5 · Sizing the plan to the work

Not every idea needs all nine sections. A one-page utility gets Concept / Goal / Backlog /
QA and a decision log that may hold two rows. **The cross-framing (§1) and the decision log
(§3.1) are never skipped** — they are cheap, and they are the failure this skill exists
for. Everything else scales.

State at the top which sections were skipped and why, so the next reader knows the omission
was a choice.

## §6 · Handoff

`PLAN.md` → `/orch-code-anth` (node by node, dependency order) → milestone alert →
`/orch-qa` (verify, ledger the passes) → findings return here as new backlog rows.
`/orch-clean` and `/orch-adversarial` feed the same return path. That loop is the point.

For a first-pass stand-up of a whole repo, use **`/orch-plan-ralph`** instead: the same
plan, plus a loop harness that drives the code phase across the entire backlog in one push.

### §6a · The first-start kick-off (greenfield callers)

When the caller started with an idea and nothing built — the common case — do not end on a
document. They have just been asked forty questions and handed a backlog, and *"now run
`/orch-code-anth` on node A1"* assumes a fluency they have already told you they lack.

End with a **KICK-OFF** block:

```
KICK-OFF — Klikor

BEFORE ANY CODE, go and get these (§9): P1 domain (~$15), P2 Stripe (2-5 days).
  Start P2 today — it is the longest pole and nothing about it is technical.

FIRST MILESTONE  M1 · "a button on a phone presses a key on the PC" — nodes A1-A4.
  Run:  /orch-plan-ralph          — stands up A1-A4 in one push
  Or:   /orch-code-anth A1        — one node at a time, if you want to watch it work

WHEN M1 LANDS you will be alerted. Then run /orch-qa — it writes the test list and
  tells you which parts you must check yourself, because a machine cannot judge
  whether it FEELS instant.

WHAT YOU WILL BE ASKED FOR   an API key for X · the phone you are testing on ·
  a decision on Q3 (how fast is fast enough) before M2 can start.
```

Rules for it, both measured as violations in live runs:

**ONE command, not two.** Offering `/orch-plan-ralph` *or* `/orch-code-anth A1` looks
generous and is not: a first-time caller has no basis to choose between them, so a menu
hands them a decision they came here to be spared. Name the one you recommend. If the other
is worth knowing about, it is a sentence *after* the block — never a second option at the
same decision point.

**Nothing in the kick-off may reference something never explained.** One run's kick-off
asked the caller for *"a yes or no on Q7, the 15-minute checkout hold"* — a question that
had never been put to them in conversation. The kick-off is read alone, after the session
ends; every term in it must already be theirs.

Also: name the single next command.
Say plainly which parts need them and which do not, because the thing a first-time caller
most needs to know is when they can walk away and when they cannot. And put the long-lead
procurement first, since it is the only work that starts before anything is built.

## Invariants

- Establish first whether the plan is about THIS repo or about an idea. Audit only in the
  first case; a concept plan skips the audit entirely.
- In an active repo, audit before asking: repo state, history, existing artifacts, and what
  the human invoked. Classify the ask (MINOR/FEATURE/MAJOR/REBUILD) out loud and let them
  correct it. A MINOR ask is told it does not need this skill.
- Reflect understanding back and converge BEFORE decomposing. Separate what the human said
  from what you derived, and say the derived list deserves the most scrutiny. Iterate until
  they confirm; record the round count; failure to converge is a finding, not a reason to
  start writing.
- Most nodes are not CRITICAL. If more than about a fifth are, you are ranking importance
  instead of blast radius.
- Push back when the ask drifts, creeps, or contradicts a logged decision. Name it, cite
  it, offer options, recommend one — then build what they decide. An overruled objection is
  logged as a rejected alternative; an unraised one is the failure.
- Interrogate before decomposing. A backlog is not a substitute for understanding.
- **Offer GUIDED vs BRIEF on the first run, with the token cost stated plainly, and default
  to GUIDED if they do not answer** — someone who could not answer that question is who
  GUIDED is for. Record the mode in the header; honour a switch whenever they ask.
- **Say up front that their mind is allowed to change.** A caller who thinks their answers
  are permanent freezes or over-commits to look decisive, and both corrupt the interrogation
  invisibly. The decision log is a revisable record, not a contract.
- **Decisions carry the date they were made, and the log is append-only.** Superseding adds
  a dated row naming the old one; nothing is edited or deleted. Reversals are the most
  valuable rows in the table.
- Plan the product, not just the program. Money, distribution, support and legal are part
  of the sweep, and they are what a technical caller skips.
- **Walk the §1.5 domain sweep every time, whether or not the caller raised any of it.** The
  default caller does not know what to ask for; a plan that only answers what it was asked
  has a hole exactly where their knowledge ends. Every domain gets a verdict in §3.11, so a
  dismissed one is distinguishable from a forgotten one.
- **"I don't know" is converted, never accepted.** Propose a default, name its consequence,
  get a yes or no, log it `ASSUMED-DEFAULT`. Asking a non-builder to close an open question
  is asking them to do the job they came here for help with.
- **Name what must be bought** — domain, payments, hosting, store accounts, certificates —
  with cost, owner and lead time. Long-lead items start in phase one regardless of when they
  are needed.
- The §2.5 confirmation is a HALT: a closed question, then the turn ends. Silence is not
  consent, and the confirming words go in the plan header. Measured: 3 of 8 planners tried
  to skip this and 2 succeeded.
- A greenfield plan ends with a KICK-OFF naming ONE next command, not a document.
- Core questions are asked in at least two frames. Contradictions are surfaced verbatim to
  the human, never reconciled silently.
- Every decision is logged as it is made, with its rejected alternative. Reversals keep
  both answers.
- The decision log is checked against later. A change contradicting a logged decision
  either adds a new decision row or does not land.
- Every node carries RISK, APPLY-TIER, depends, a deterministic accept command, and QA IDs.
- **Per milestone, at least one NODE accept drives the composed product from outside** —
  starts it, acts on it, asserts the outcome. Measured: 16 green node accepts and 74
  passing tests shipped on a product whose endpoint was a no-op. On the milestone it is
  prose a loop refuses to run; on a node it is supervision.
  A node without an accept command is not a node, it is a wish — and a node whose check
  duplicates its neighbour's is one node, not two.
- Priority uses only axes the coder routes on: RISK, APPLY-TIER, dependency order, P0–P3.
- Re-running merges: decisions append, nodes reconcile by ID, completed nodes stay
  completed. Never clobber a plan.
- QA authority (AUTO vs OWNER, per area) is asked during planning and written into the plan
  header. Never assumed. CLASS (MACHINE/HUMAN) is tracked separately from AUTHORITY.
- Milestones are defined so a human can exercise them; completing one alerts rather than
  auto-runs.
- Speculative nodes are kept and re-decided, not deleted and not built.
