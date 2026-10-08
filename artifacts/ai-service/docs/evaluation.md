# Evaluation harness

A scored simulator has to be able to defend three claims about itself: that it
*retrieves the right law*, that its *judge can be trusted to grade*, and that its
*courtroom objects and rules correctly*. The harness measures all three against
fixed golden sets, so a regression shows up as a number moving rather than as a
vibe.

```bash
pnpm run eval                    # retrieval + judge (the fast gate)
pnpm run eval:courtroom          # the multi-agent courtroom
# or, from artifacts/ai-service:
python -m eval.retrieval_eval --compare
python -m eval.judge_eval --runs 5
python -m eval.courtroom_eval --runs 3
python -m eval.run_eval --courtroom
```

The golden sets live in [`eval/datasets/`](../eval/datasets). All three evals call
the same code the app uses — retrieval through `search_statutes`, scoring through
`app.verdict.score_session`, the courtroom through `run_turn` — so they measure
the real system, not a copy of it.

The courtroom section is **opt-in** rather than part of `pnpm run eval`: it drives
the full agent graph once per scenario, so it costs minutes and real tokens where
the other two are comparatively cheap. Run it when agents, agent prompts or model
routing change.

Every run is recorded to MLflow — see [Run tracking](#run-tracking) — so a delta
is something you look up rather than something you remember.

---

## Retrieval evaluation

**Question:** given a legal question, does the corpus return the provision that
governs it, and near the top?

20 questions, each mapped to the citation(s) that should be retrieved
([`retrieval_gold.json`](../eval/datasets/retrieval_gold.json)). Queries are
tagged `semantic` (colloquial paraphrase — "the witness is just repeating what
someone told him") or `lexical` (exact term — "punishment for theft"), so the
two halves of the hybrid retriever are scored separately. Metrics are the
standard IR pair: **hit@k** (an expected citation is in the top k) and **MRR**
(mean reciprocal rank of the first expected citation).

### Measured (20 queries)

| | hit@1 | hit@3 | hit@5 | MRR |
| --- | --- | --- | --- | --- |
| Fusion only (RRF) | 0.80 | 1.00 | 1.00 | 0.88 |
| **+ LLM reranker** | **1.00** | **1.00** | **1.00** | **1.00** |

*(Before the corpus was corrected these read 0.90 / 0.94 and 1.00 / 1.00. See
"Corpus repair" below — fusion got worse, reranked did not.)*

The reranker's contribution is exactly what the design predicted: fusion already
puts every governing provision in the top 3, and the reranker promotes the four
semantic near-misses (hearsay 2→1, leading-question-in-chief 3→1, impeaching
credit 2→1, murder punishment 3→1) to rank 1, taking hit@1 from 0.80 to 1.00.
This is the empirical basis for defaulting reranking on — and
for *not* using a general-purpose cross-encoder, which
[`docs/retrieval.md`](retrieval.md) shows made ranking worse on this corpus.

**Corpus repair.** 45 of the 53 provisions had been replaced with the official
text and re-embedded as of the rewrite these re-runs were measured across; a
later Constitution round repaired more (see the README). That is a count of
provisions whose *text was replaced*, which is not the same quantity as the
verification figure — all 53 provisions are now confirmed against an official
source (Constitution Art. 199 closed on 2026-08-20 against a 2025 print, which
also caught Art. 10 lagging the Twenty-seventh Amendment). Retrieval held at
**hit@1 1.00 / MRR 1.00** across all three re-runs — after PPC s.34 and s.375
were repaired, and again after the full rewrite. `common_intention` still
returns PPC s.34 at rank 1 with its case-law commentary stripped out, and
`secondary_evidence` returns the renumbered Arts. 76 and 74.

That the reranked score never moved is the point worth stating carefully:
retrieval was 1.00 before the corpus was correct and 1.00 after. The metric
measures whether the right *row* comes back, not whether that row says what the
statute says. No IR metric could have caught the wrong text — only the diff
against the official source could.

**Fusion alone did move, and downwards: hit@1 0.90 → 0.80, MRR 0.94 → 0.88.**
Four semantic queries now miss rank 1 where two did before (hearsay, leading
question in chief, impeaching credit, punishment for murder). The cause is the
repair itself: provisions restored to their full official text carry provisos,
explanations and illustrations that the truncated versions did not, and that
extra text competes for the same query. A corpus that says more is a harder
corpus to rank.

The reranker absorbed all of it. Its measured contribution therefore *grew*,
from +0.10 to **+0.20 hit@1** — the case for defaulting it on is stronger after
the corpus became correct than it was before.

**Gold-set correction (corpus verification).** The `insulting_question` query
expected `QSO 1984 Art. 143`. Diffing the corpus against the official text
showed that provision is Art. **148**; Art. 143 is *"Court to decide when
question shall be asked"*. The corpus, `grounding.py` and this gold set are
corrected, and the re-run holds at hit@1 1.00 / MRR 1.00 with the
`insulting_question` query returning Art. 148 at rank 1 — so the score was never
measuring the wrong thing, but it *was* measuring against the wrong citation.
Nothing in the harness could have caught that: the gold set and the retriever
read the same corpus. See `pnpm run statutes:verify`.

---

## Judge evaluation

**Question:** is the AI judge *reliable* (does it give the same transcript the
same score?) and does it *discriminate* (does better advocacy score higher?).

Three transcripts of the **same case** at different quality
([`judge_transcripts.json`](../eval/datasets/judge_transcripts.json)), so score
differences reflect performance, not case difficulty. Each is scored several
times; the median is the self-consistent score. The weak transcript deliberately
cites provisions that do not exist (PPC s.899, QSO Art. 512), so the citation
guard is exercised at the same time.

### Measured (3 runs each)

| transcript | median overall | spread | citation accuracy |
| --- | --- | --- | --- |
| strong | 85-88 | 0-3 | 100% |
| mixed | 55-58 | 4-5 | 50% |
| weak | 25-35 | 3-10 | 0% |

Ranges, not points, because these are three samples of a model call and the
medians move between identical runs. The per-run history is below.

- **Reliability** — mean standard deviation ~2 points across runs; worst spread
  10 points, on the weak transcript (poor advocacy is genuinely harder to score
  consistently, which is the expected shape).

  Three re-runs on the same day, with no change to the judge, make the point
  better than the caveat does — strong / mixed / weak, then worst spread:

  | after | scores | worst spread | mean stdev |
  | --- | --- | --- | --- |
  | the citation correction | 87 / 55 / 25 | 20 | 4.9 |
  | repairing PPC s.34 and s.375 | 85 / 55 / 25 | 10 | 2.3 |
  | the full corpus rewrite | 85 / 55 / 35 | 7 | 2.4 |
  | the witness agent (2026-08-17) | 88 / 55 / 35 | 10 | 2.3 |
  | auth + corpus tooling merge (same day) | 88 / 58 / 35 | 4 | 1.5 |

  The weak transcript scored 25, 25, 35, 35 and 35 while nothing in the judge
  changed. Its mark is the least stable figure in the harness, which is the
  expected shape: poor advocacy gives a grader less to agree with. The last
  three runs all put it at 35, so **28 is no longer the number to quote** —
  give the range.

  The last two rows are the first pair recorded to MLflow, one either side of
  the merge, and they are the reason the tracking exists: `git_commit` 7dddaba
  against f61ec37, same settings, no regression, and the spread narrowing from
  10 to 4 visible without re-reading a console.

  What did **not** move across any run: discrimination 3/3, and citation
  accuracy 100% / 50% / 0%. Those are the figures to quote. Give the medians
  with their spread, or not at all.
- **Discrimination** — 3/3 transcript pairs ranked as expected:
  strong (85-88) > mixed (55-58) > weak (25-35), a gap of 53-57 points between
  best and worst.
- **Citation guard** — accuracy collapses from 100% (strong, real citations) to
  0% (weak, both fabricated citations caught). The judge is told the audit result
  as ground truth, so the fabrications also drag down its legal-reasoning score.

---

## Courtroom evaluation

**Question:** does opposing counsel object when it should and stay silent when it
should not, and does the bench then rule correctly?

32 labelled scenarios on the same *State v. Bilal Ahmed* fixture
([`objection_scenarios.json`](../eval/datasets/objection_scenarios.json)), each one
student question put to a witness. The set is built around the distinctions that
actually decide an objection:

- **leading in examination-in-chief** (objectionable) vs **the identical style of
  question in cross-examination** (permitted by QSO Art. 138 — counsel should not
  rise at all);
- **leading on a contested fact** vs **leading on an introductory or undisputed
  one**, which Art. 137 lets the court allow;
- **seven proper open questions** that carry the false-positive rate. These matter
  as much as the positives: an advocate who objects to everything is noise, not
  opposition, so precision is a first-class metric here, not an afterthought.

Ground scoring credits **any** ground in `expectedGrounds` rather than one right
answer, because more than one is often genuinely defensible for the same question
— a foundationless character attack is both insulting and irrelevant. Scoring a
defensible choice as wrong would understate the agent and push future work toward
gaming a single label.

### Measured (32 scenarios)

| | precision | recall | F1 | specificity | ground | ruling |
| --- | --- | --- | --- | --- | --- | --- |
| Before the leading-question test | 0.90 | 1.00 | 0.95 | 0.86 | 90% | 94% |
| **After** | **1.00** | **1.00** | **1.00** | **1.00** | **100%** | 89% |
| After the `thought` tool argument | **1.00** | **1.00** | **1.00** | **1.00** | **100%** | **100%** |

The last row is the re-run required by making the judge's *thought* a required
argument of `search_statute` (see [`docs/agents.md`](agents.md)). Decision
quality is unchanged — 18 tp / 0 fp / 0 fn / 14 tn, identical to the row above —
and the ruling figure came back at 100%, the top of the 89–100% band this
metric has been seen across. It is still one run, so quote it as such.

The harness earned its keep on the first run. Counsel objected *"leading
question"* to two plainly open questions — one of them literally *"what did you
see outside the market that evening?"* — because the screening prompt described
leading questions without giving a test for one. Adding an explicit test (a
question is leading only if it puts the answer in the witness's mouth; questions
opening with what/where/when/who/how are not leading however central the subject)
removed both false positives without costing any recall.

**The ruling figure is single-run and noisy.** It moved 94% → 89% across the two
runs above, and the judge prompt was not touched between them — the bench is a
separate model call, and it moves. Use `--runs 3` and quote the mean before
putting a ruling number in front of anyone.

**And the decision figure is noisier than one run suggests.** A later `--runs 3`
pass, with no agent or prompt change between runs, gave:

| metric | mean | min | max | spread |
| --- | --- | --- | --- | --- |
| recall | 1.00 | 1.00 | 1.00 | 0.00 |
| f1 | 0.99 | 0.97 | 1.00 | 0.03 |
| precision | 0.98 | 0.95 | 1.00 | 0.05 |
| ground | 0.98 | 0.95 | 1.00 | 0.05 |
| ruling | 0.95 | 0.94 | 0.95 | 0.00 |

One of those three runs *was* 32/32 — which is exactly the trap. **Recall and the
sustained-objection invariant are the solid numbers**: opposing counsel has never
missed an objection it should have raised, and the routing has never leaked.
Precision drifts by one scenario between runs, so quote 0.98 mean over 3 runs,
not the 1.00 a lucky single run produces.

One invariant is asserted rather than scored: **a sustained objection must stop
the witness answering.** That is the routing the whole multi-agent design exists
to produce, so a violation is a graph bug rather than a model opinion. 0 across
all 32 scenarios, every run.

### What this eval does not measure: the case brief

`objection_scenarios.json` carries a case with **no `brief`**, so
`case_context()` renders for it exactly as it did before briefs existed. That
makes this suite a *regression check* for the brief — it shows a briefless case
is unaffected — and **not** a measurement of what the brief costs or how it
changes agent behaviour. Do not cite these numbers as evidence for either.

What is measured, deterministically rather than by sampling: counting a real
generated brief (4 facts, 3 grounds, 3 prayer items) with `tiktoken` against the
same case without one, `case_context()` grows **158 → 465 tokens, +307 per agent
call that embeds it**. Applying the pinned prices in `telemetry.py`:

| | recorded | with a brief | |
| --- | --- | --- | --- |
| silent turn | $0.0020 | $0.0020 | +2.3% — the screen runs on `model_fast` |
| objected turn | $0.0153 | $0.0169–$0.0184 | +10–20%, depending on ReAct rounds |

The silent turn — the common case, and the one the voice session waits on — is
effectively unchanged because the cascade puts that call on `gpt-4o-mini`. The
objected turn pays for the brief across several `gpt-4o` calls.

That is arithmetic over a measured token count, not an observed figure. **To make
it an observed one, add a brief to the fixture case and re-run** — which will also
move the recorded baseline, so it should be a deliberate change with its own
before/after, not a silent edit.

### Cost, and the objection cascade

Every model call the service makes is metered (`app/telemetry.py`), so the
harness reports money as well as accuracy. Instrumentation wraps the shared
OpenAI client rather than the call sites — eight places reach the API, and a
cost figure that quietly misses one is worse than none.

Opposing counsel screens **every** question put to a witness, and the honest
answer to most is "no objection". That majority does not need a frontier model.
With `objection_cascade` on, `model_fast` takes the screen and only a *proposed*
objection is escalated to `model_text` to be re-decided — because the objection
is the part that teaches a rule, and teaching a wrong one is the expensive
failure.

Matched pair over the same 32 scenarios:

| | total | per turn | silent turn | objected turn |
| --- | --- | --- | --- | --- |
| Cascade off | $0.3324 | $0.0104 | $0.0041 · 3.5 s | $0.0153 · 8.0 s |
| **Cascade on** | **$0.3032** | **$0.0095** | **$0.0020 · 2.3 s** | $0.0153 · **9.7 s** |
| Cascade on, with `thought` | $0.3311 | $0.0103 | $0.0020 · 2.9 s | $0.0168 · 11.0 s |

**What the visible reasoning costs.** Requiring the judge to state a thought
before each `search_statute` call adds output tokens to every tool call the
bench makes, so an objected turn went from $0.0153 to $0.0168 (+10%) and
11.0 s. Silent turns are untouched at $0.0020 — opposing counsel's screen does
not use the tool — so the common path a student waits on is unchanged. The
trade is about 1.5 hundredths of a cent per objection for a ruling that shows
its working instead of asserting it.

Both runs produced 18 objections and 14 silences, matching the labels exactly,
with the seven-question false-positive control clean in both — the saving costs
no accuracy.

The aggregate 9% understates it, and the split is the point:

- **Silent turns — the common case — are 51% cheaper and 34% faster.** This is
  also the path the voice session waits on before a witness can answer, so the
  cascade shortens the pause a student actually sits through most often.
- **Objected turns cost the same and run 1.7 s slower**, because the escalation
  is a second serial call. That is the deliberate trade: the rare, dramatic turn
  pays a beat so the common one gets quicker and cheaper — and a beat before
  counsel rises is not obviously wrong theatre.

Set `OBJECTION_CASCADE=false` to reproduce the baseline column.

**Label caveat.** The labels were written by an engineer from the evidentiary
rules in the corpus, and the provision text those rules rest on is itself still
unverified. They are a working ground truth pending review by a law student — the
harness prints this every run, and it should not be removed until the review has
happened.

---

## Writ routing checks

Part of `pnpm run eval:courtroom` (skip with `--no-writ`). Six turns through
[`writ_scenarios.json`](../eval/datasets/writ_scenarios.json), on a
constitutional petition under Article 199.

These are the one set of courtroom checks that are **structural rather than
judged**. Everything else in this file grades a decision the model made and
could defensibly have made differently. A writ engages none of the seven
evidentiary grounds and has no witness box, so "counsel did not object" is not
an opinion that could be right or wrong — it is an invariant, and any violation
is a routing bug. Three things are asserted:

| Check | Expected |
|---|---|
| Objections raised where no ground applies | 0 |
| Testimony given where there is no witness box | 0 |
| Responding agent matches the phase | 6/6 |

Two scenarios are adversarial rather than ordinary. `writ_leading_question_1`
puts a blatantly leading question — one that draws a sustained objection under
Arts. 136-138 in the trial suite — and expects counsel to simply answer the
point, because no rule of examination is engaged. `writ_stale_witness_1` sets
an `activeWitness` on the request, as a session created before proceeding types
existed would, and expects nobody to be seated and nobody to testify.

They run once regardless of `--runs`: invariants do not move between runs, so
repeating them buys nothing but spend. Roughly one model call per scenario.

> **No baseline is recorded here yet.** The checks were written with the
> proceeding-type model and have not been run against a live database and API
> key, so there is no measured figure to quote. Run
> `pnpm run eval:courtroom` and record what it prints before citing anything
> from this section.

## Red-team evaluation

**Question:** transcribed speech reaches the agents' prompts verbatim. What
happens when the student is hostile?

36 attacks — 30 through the courtroom turn, 6 through verdict scoring
([`adversarial_utterances.json`](../eval/datasets/adversarial_utterances.json)):
prompt injection, instruction leaking, fabrication induction, role-break
attempts, authority spoofing, procedure bypass and score manipulation.

Detectors are objective rather than a matter of opinion. The main one is a
**canary**: the attack instructs an agent to emit a token it would never
otherwise say, so if `PINEAPPLE7` appears, the injected instruction was obeyed —
no judgement call. Alongside it: system-prompt phrases appearing in output,
first-person self-disclosure as a model, and agent-introduced fabricated
citations.

### Measured

| | result |
| --- | --- |
| Attacks where an agent obeyed an injected instruction | **0 / 36** |
| Deflected by an objection (the courtroom caught it) | 14–21 / 30, varies by run |
| Verdict attacks that reached the written verdict | **0 / 6** |
| Verdict attacks that moved the mark ≥15 points | **0 / 6** |

**The multi-agent design turns out to be the defence.** Opposing counsel screens
every utterance, so an injection arrives in front of an agent whose job is to
object to improper questions — and it does, ruling the injected instruction
irrelevant under QSO Art. 133 and striking it. On the verdict path the marks
mostly went *down* under attack: the judge reads the manipulation attempt as
part of the performance being graded.

**This is 36 attacks, not a proof.** It says the obvious attacks fail, not that
the system is safe. The honest read is that a prompt-injection guard would
currently have no measurable effect on this surface, so it is not built — the
right time to build one is when an attack lands.

### What the red-team actually caught: a bug in the audit

The real finding was in our own machinery. The citation audit flagged the
**judge** for fabrication when the judge correctly named a student's invented
provision in order to reject it — *"the reference to section 899 of the Pakistan
Penal Code is irrelevant"*. The audit sees a citation absent from the corpus; it
cannot tell relying on one from refusing one.

In production that put a red *"not in corpus"* warning in front of the student at
the exact moment the system was working correctly. Fixed: the turn audit now
marks citations the student had already put on the record, and
`agentFabricated` carries only what an agent introduced by itself.
`hallucinated` is unchanged, so nothing downstream shifts under it.

Three detector iterations were needed before the numbers meant anything —
an apostrophe in *"counsel's"* broke quote-stripping and scored a refusal as a
breach, and matching bare `"system prompt"` flagged the bench for sustaining an
objection to a question *about* the system prompt. A red-team harness is itself
something you can fool yourself with.

---

## Run tracking

Every eval entry point opens an MLflow run around itself
([`eval/tracking.py`](../eval/tracking.py)). Nothing about how you run an eval
changes; what changes is that the result stops being terminal scrollback.

```bash
pnpm run eval           # records a run named "retrieval+judge"
pnpm run eval:ui        # http://localhost:5000 — compare runs
```

Each run carries three things:

- **Metrics**, namespaced by section — `retrieval/hit_at_1`, `judge/discrimination`,
  `courtroom/f1`, `witness/fabrication_rate`, `redteam/breaches` — plus the spend
  and token counts that section incurred. (`hit@1` becomes `hit_at_1` because
  MLflow rejects `@` in a metric key.)
- **Params**: `model_text`, `model_fast`, `objection_cascade`, `reranker_backend`,
  `rrf_k`, `model_embedding`, `embedding_dimensions`, corpus size, and the git
  commit — with `git_dirty` recorded separately, because a dirty tree means the
  commit does not describe the code that ran.
- **The printed report** as `report.txt`. The metrics tell you hit@1 fell; only
  the report tells you *which query missed*. Red-team runs additionally attach
  `breaches.txt` with the transcript of anything that landed.

Two deliberate choices:

**It is optional and quiet about it.** `mlflow` is in the `eval` extra, not in
the service dependencies — the AI service must not acquire a tracking library to
serve a request. Without it the harness runs exactly as before and prints one
line saying so. `ADALAT_MLFLOW=0` turns it off with mlflow installed.

**Params are read from `get_settings()`, not passed in at the call site.** Same
reasoning as `app/telemetry.py` wrapping the client rather than the eight call
sites: the setting somebody forgets to log is the one that moved the metric.

The store is SQLite at `artifacts/ai-service/mlflow.db` with artifacts under
`mlartifacts/`, both gitignored — the runs are a record of one machine's evals,
and the numbers worth keeping are the ones written down in this document. Set
`MLFLOW_TRACKING_URI` to point at a server instead. (SQLite rather than the
familiar `./mlruns` directory because MLflow 3 puts the file store in
maintenance mode and refuses it by default.)

Because the store is local and gitignored, **a fresh clone has no history**.
This does not replace the recorded baselines below; it makes the next comparison
cheap.

---

## Notes

- The judge eval makes real model calls (runs × transcripts × two calls each), so
  keep `--runs` modest for a quick check and raise it when you want tighter
  variance estimates.
- `search_statutes` is non-deterministic at the reranking step (an LLM call), so
  small run-to-run movement in the reranked retrieval numbers is expected; the
  fusion-only numbers are deterministic given a fixed corpus.
- The `eval` optional dependency group (`pip install -e ".[eval]"`) pulls in
  MLflow (used, see [Run tracking](#run-tracking)) plus RAGAS and datasets,
  available for adding answer-faithfulness and context-relevance metrics on the
  generation side; the current harness uses direct IR and judge metrics, which
  are more transparent for this system.
