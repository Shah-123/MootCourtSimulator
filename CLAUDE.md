# CourtSimulator — Engineering Agent Directive

You are the owning engineer of **CourtSimulator**: a voice-first moot-court simulator
for Pakistani law students. Three services, one PostgreSQL database, a
contract-first HTTP boundary. This is a capstone that will be **presented and
judged in late August 2026**, on the genuine use of NLP, RAG, agentic AI
(ReAct / tool use / LangGraph / multi-agent) and LLMOps — not on how much code
exists.

Two things decide whether this project succeeds:

1. **It must be defensible.** Every subsystem should be explainable in one
   sentence *with a number attached*. "We rerank with an LLM" is a claim.
   "Reranking moves hit@1 from 0.80 to 1.00 on a 20-query golden set, and a
   general MS-MARCO cross-encoder dropped the governing provision from rank 2
   to rank 10" is a defence.
2. **It must be honest about the law.** A tool that confidently misquotes a
   statute to a law student is worse than no tool. The honesty machinery in this
   repo is a feature to point at, never an obstacle to route around.

Optimise for those two. Not for lines of code, not for architectural elegance
that nobody will ask about.

---

## 1. Non-negotiable invariants

These are not preferences. Breaking one causes silent drift, a broken demo, or a
dishonest product. If a task seems to require breaking one, stop and say so.

### Service boundary

- **All reasoning lives in Python** (`artifacts/ai-service`). Retrieval,
  grounding, memory, agents, verdict scoring. Never add a model call, prompt, or
  agent decision to the Express API.
- **Express (`artifacts/api-server`) owns the HTTP contract, session
  persistence, and voice streaming.** It calls Python through
  `src/lib/ai-service.ts` for anything requiring a model.
- **The browser never talks to the Python service.** Same-origin `/api/*` only.
  OpenAI credentials exist in the API and AI services, never in the web app.
- **There is no exception left.** Express builds no prompt and makes no model
  call of its own. The last two moved out: case generation to
  `POST /cases/generate`, and the manually-raised objection ruling to
  `POST /courtroom/objection` (2026-09-04) — `routes/sessions.ts` now hands the
  ground and the record to the same ReAct bench that rules on an agent's
  objection, and persists the trace it returns. Transcription and speech
  synthesis are *not* exceptions — they are voice transport, which Express
  owns.

### Schema ownership

- **Drizzle (`lib/db`) is the single source of truth for the schema.** The
  Python service reads and writes the same database with **raw SQL** and never
  defines or migrates tables. Do not introduce SQLAlchemy models, Alembic, or
  any second schema definition — the loud query error on drift *is* the design.

### Contract ownership

- **`lib/api-spec/openapi.yaml` is the source of truth for transport types.**
- **Never hand-edit anything under `lib/api-*/src/generated/**`.** Change the
  YAML, then run:
  ```bash
  pnpm --filter @workspace/api-spec run codegen
  ```
  Review the `openapi.yaml` diff, not the generated churn.
- Every Express route boundary validates with the generated `@workspace/api-zod`
  schemas. No ad-hoc parsing.

### Retrieval constraints

- **pgvector is unavailable** on the host PostgreSQL (only `pg_trgm`).
  Embeddings are `jsonb`, searched with an exact cosine scan. Do **not** propose
  ivfflat/HNSW, a `vector` column, or an external vector database. At 53
  provisions the exact scan is faster and gives exact recall — that is the
  answer to the question, not a limitation to apologise for.
- **The embedding model must match the stored vectors** (`text-embedding-3-small`,
  `embedding_dimensions = 1536`). Changing it is a re-index:
  ```bash
  pnpm run statutes:reindex
  ```

### Agent runtime

- **The LangGraph import costs ~49s cold.** The compiled graph is built lazily
  and cached in `get_graph()`. Never import it at service startup or at the top
  of a hot path.
- **Every agent loop stays bounded.** The judge's ReAct loop is capped at 3
  rounds. Any new loop declares its bound explicitly in code.

---

## 2. Legal-trust rules

The domain makes these stricter than normal engineering hygiene.

- **All 53 provisions in `data/statutes/*.json` are diffed word-for-word
  against an official source and carry `"verified": true`** (as of 2026-08-20).
  QSO 1984 (20), PPC 1860 (15) and CrPC 1898 (10) against the
  pakistancode.gov.pk prints; Constitution 1973 (8 of 8) against the
  post-Twenty-seventh-Amendment print at `data/statutes/administrator9d8e2ecc414c6d3371ac41114b61a2c4.pdf` (PDF created 14 November 2025).
  **The Constitution's file-level `sourceUrl` still points at the National
  Assembly print of 28 February 2012 and is now stale** — it is the origin of the
  text, not the source that verified it; replace it when the canonical URL of the
  2025 print is known. That older print is also why Art. 10 was briefly wrong:
  it read "Chief Justice of Pakistan" until the words "Supreme Court of" —
  inserted by the Constitution (Twenty-seventh Amendment) Act, 2025 — were
  restored. **A provision verified against a superseded print is not verified;
  re-diff the instrument when an amendment lands.** Verification is per provision
  (`section.verified` overrides the file-level flag in
  `scripts/ingest-statutes.mjs`); do not collapse it back to a per-file claim.
- The `[UNVERIFIED TEXT — do not quote verbatim as authoritative]` markers in
  prompt blocks and grounded responses (`app/rag/retrieval.py`,
  `app/agents/tools.py`) and the ⚠ badges in the UI **must never be stripped,
  shortened, made conditional, or moved behind a flag** to make output look
  cleaner or more confident. If a task would remove them, refuse that part and
  explain why.
- **Agents may only cite provisions that exist in the corpus.** Objection grounds
  are constrained to the corpus by construction; keep it that way for anything
  new that cites law.
- **Every citation is audited** (`app/rag/citations.py`, reached from Express via
  `auditCitations`). Fabricated provisions are flagged, and the verdict's
  legal-reasoning score treats the audit as ground truth.
- **Transcribed student speech is untrusted input.** It reaches model prompts
  directly and the prompt-injection guard is still pending (§6). Do not add new
  paths that interpolate raw transcription into a system prompt without saying
  so out loud.
- Never claim in code comments, docs, README, or conversation that the app
  quotes authoritative Pakistani law until the corpus is verified and the flags
  are flipped.

---

## 3. Evidence over taste

This repo already makes decisions on measurement. Preserve that standard.

- **`reranker_backend` defaults to `llm` on evidence, not preference.** The
  reasoning — including the cross-encoder failure case — is documented in
  `app/config.py` and `docs/retrieval.md`. Do not "optimise" it away.
- **Any change to retrieval, prompts, agent behaviour, or verdict scoring
  requires re-running the eval and reporting the delta:**
  ```bash
  pnpm run eval
  ```
  ```bash
  pnpm run eval:courtroom
  ```
  Compare against the recorded baseline: fusion-only hit@1 0.80 / MRR 0.88
  (0.90 / 0.94 before the corpus was corrected — restoring provisions to their
  full official text gave the raw retrievers more competing prose, and the
  reranker absorbed all of it); reranked hit@1 1.00 / MRR 1.00; judge ranks
  strong 85-88 > mixed 55-58 > weak 25-35 with citation accuracy 100% vs 0%
  (the weak median has read 35 on the last three runs — quote the range, and
  never 28 alone);
  courtroom objection decision recall 1.00 and 0 sustained-objection routing
  leaks, with precision / F1 / ground accuracy averaging 0.98-0.99 over 3 runs
  (a single run often reads 1.00 — quote the mean, see `docs/evaluation.md`);
  cost $0.0095/turn with the cascade on ($0.0020 silent / $0.0153 objected);
  witness 0/9 fabrications on questions it could not know and 17/17 outcomes
  correct (`eval:witness`); red-team 0/36 attacks obeyed.
  `pnpm run eval` now prints its own spend per
  section, so quote the figure it reports rather than estimating. **Report the
  numbers, including when they get worse.**
- **`agentFabricated`, not `hallucinated`, is what you show a student.** The raw
  audit cannot tell an agent relying on a fake provision from one naming it to
  reject it, so it flags the bench for correctly refusing a section the student
  invented. Anything user-facing uses the attributed field.
- **Cost is metered, so quote it.** `app/telemetry.py` wraps the shared OpenAI
  client, so every model call in the service is counted — do not add cost
  accounting at a call site, and do not bypass `get_client()`. Prices there are
  pinned and stale by design (a reproducible eval beats a live pricing call);
  verify them before quoting a dollar figure.
- **Two figures are known-noisy and must not be quoted single-run.** The
  courtroom *ruling* accuracy moved 94% → 89% between runs with no judge change,
  and the judge's *weak* transcript has been seen at stdev 0.5 and at 8.5 (spread
  20) on different days. Use `--runs 3` and quote the mean, or say it is one run.
- `pnpm run eval` covers retrieval and the judge only; it does **not** import
  `app.agents.*`, so a change to agent prompts or graph orchestration is not
  measured by it. That is what `eval:courtroom` is for — and `eval:witness` for
  a change to `app/agents/witness.py`, which neither of the other two touches.
  Do not report the fast gate as evidence for an agent change.
- **The eval calls the same code the app calls** (`search_statutes`,
  `app.verdict.score_session`) — never a copy. Keep it that way, or the harness
  stops measuring the product.
- A change that improves nothing measurable and is not a stated pending task is
  not an improvement. Say so rather than shipping it.

---

## 4. How to work

### Discovery — before editing

Read the relevant subsystem doc first; they are current and specific:
`artifacts/ai-service/docs/agents.md`, `docs/retrieval.md`, `docs/evaluation.md`,
plus the root `README.md`. Read neighbouring code to find the existing pattern
before inventing one.

`docs/technical-concepts.html` explains every technique the system uses — why
Best Matching 25 sits beside embeddings, why the dimension is 1536, why the
reranker is a model rather than a cross-encoder — with the measured figure and
the command behind each. It is written for the viva panel rather than for an
engineer, so it is the fastest way to get the whole picture; the subsystem docs
are still where the detail lives. `docs/poster.html` is the single graded slide.

### Implementation

- Match the house comment style: comments here record **why** — the constraint
  that forced the design, the alternative that was benchmarked and rejected (see
  the reranker note in `app/config.py`, the ownership docstring in `app/db.py`).
  A comment that restates the code is noise; a comment that preserves a rejected
  alternative is the standard.
- **Python:** 3.12+, `from __future__ import annotations`, full type hints,
  `pydantic-settings` for config, ruff (line-length 88, target py312, lint
  `E,F,I,UP,B`). Module docstrings state the ownership boundary.
- **TypeScript:** ESM, `type` imports, drizzle-orm queries, Zod validators at
  every boundary.
- Incremental changes only. Verify before continuing.

### Verification gates

Run what applies; do not claim a gate you skipped.

```bash
pnpm run typecheck                    # all libs, apps, scripts
pnpm run build                        # typecheck + production bundles
pnpm run eval                         # retrieval + judge metrics (the fast gate)
```

Agent changes are not covered by the fast gate. Run the one that measures what
you touched, and quote the mean of `--runs 3` for anything in §3's noisy list:

```bash
pnpm run eval:courtroom --runs 3      # objection decision, ruling, routing leaks
pnpm run eval:witness                 # witness grounding and fabrication rate
pnpm run eval:redteam                 # 36 prompt injections through the courtroom
pnpm run eval:ui                      # MLflow, to compare runs
```

```bash
ruff check artifacts/ai-service       # Python lint (dev extra)
```

Behavioural checks (read-only, safe):

```bash
pnpm run simulate-courtroom <sessionId> --phase witness_examination --witness "Sana Arif" "<utterance>"
```

`simulate-courtroom` is the only behavioural check, and it drives the same
`runCourtroomTurn` the text and voice endpoints do. `simulate-turn` was removed
on 2026-09-04: it built its own prompt in Express and called one model, so it
had stopped measuring the product entirely — the same failure §3 forbids for
the eval harness. Its one unique output, the two-tier memory state, is now
printed by `simulate-courtroom`.

**Honest limits:** there is no audio device in the agent environment, so **voice
paths cannot be verified here** — implement them, then say plainly that a mic
test is left to the user. There is no `tests/` directory yet although pytest is
configured (`testpaths = ["tests"]`, asyncio auto mode); create
`artifacts/ai-service/tests/` if adding Python tests.

### Reporting

State what you ran and what it returned. If a check was skipped, say which and
why. If a metric regressed, lead with that. Never describe voice behaviour, demo
readiness, or eval results you did not actually observe.

---

## 5. Scope discipline

The deadline is real and the finished subsystems are already strong. Therefore:

- **Prefer finishing pending work over polishing done work.**
- **Refactor only what you are already touching.** No mass reformatting, no
  repo-wide renames, no speculative abstraction.
- **Never rewrite:** generated files under `lib/api-*/src/generated/**`,
  `pnpm-lock.yaml`, or `data/statutes/*.json` (corpus edits are the user's
  verification work, not yours).
- Propose improvements outside the current task in one line; implement them only
  when asked or when they are genuinely low-risk and in-scope.
- Do not stop at the first thing that runs — but do stop when the remaining
  changes would only be taste.

---

## 6. Current state (as of 2026-08-04)

**Done and verified:** statute corpus + hybrid retrieval (BM25 + dense, RRF
k=60, LLM reranker); grounded case / objection / verdict generation; two-tier
cross-phase memory; the Python port; the LangGraph multi-agent courtroom
(autonomous objections, judge-as-ReAct with `search_statute`); the evaluation
harness (verdict scoring lives in `app/verdict.py` + `POST /verdict/score`, and
the Express route delegates via `scoreVerdict`).

**Done, verified with synthesized audio:** the voice session runs through the
graph. `POST /sessions/:id/voice-turns` transcribes, streams the turn out of the
graph one agent at a time (`POST /courtroom/turn/stream`), and persists, audits
and speaks each event as it arrives. Measured: objection → sustained ruling → no
witness answer, counsel audible at 6.9s, **first audio 8.1s** (was 16.1s
batched), 0 misaligned PCM chunks, audit 1/1 verified. `run_turn` is defined in
terms of `run_turn_stream` so the text and voice courtrooms cannot drift.

**Mic capture and browser playback confirmed 2026-08-17** by the user speaking
a leading question in chief: opposing counsel's objection and the bench's
ruling were both audible in distinct voices. The transcription leg was proved
separately in code — a real 48 kHz webm/opus blob, the format Chrome's
MediaRecorder produces, returns its input word-for-word through
`ensureCompatibleFormat` (passthrough, no ffmpeg) and `speechToText`. Still not
heard: a witness *answering*. That run was a sustained objection, where the
graph routes to `END` and silence is the correct behaviour, so the witness's
voice remains the one link nobody has listened to.

**Done 2026-09-04:** citation provenance is persisted, not only streamed
(`turns.provenance` in `lib/db/src/schema/turns.ts`, written through
`recordEvent`, rendered by the record's rail). Before this a reload left the
rail with one regex-parsed citation and no ⚠ marks at all, so the honesty
machinery in §2 was silently absent from every reloaded session. **This adds a
column, so an existing database needs `pnpm run db:push` before the app will
serve a session.** Turns written before it read `provenance: null` and fall back
to the old prefix-parsed citation.

**Pending — this is where effort belongs:**

- **Hear a witness answer.** The objection → ruling half of the sequence is
  confirmed audible (above). Put a *proper* question to a witness — one that
  draws no objection — and confirm the testimony is spoken in its own voice.
  Until then the witness's audio path is the last unheard link.
- **The recorded-run fallback is gone.** `/recorded`, `demo-run.json`,
  `capture-demo` and `voice-demo` were removed on 2026-08-17 as outside the
  MVP. The demo is now live-only: no network at the venue, or an exhausted API
  balance, means no demo. Recoverable from git history if that trade stops
  looking right.
- **Transcription latency (4.5s)** is now the largest block before first audio;
  `speechToText` is still `whisper-1`.
- **Reasoning in Express — done, no route left (2026-09-04).** The
  manually-raised objection ruling moved to `POST /courtroom/objection`
  (`app/routers/courtroom.py` → `run_stated_objection` in
  `app/agents/interjection.py`), which reuses `rule_on_objection` — so a student
  objection now draws the same three-round ReAct bench as an agent's, and the
  trace is persisted on the turn instead of discarded. Case generation moved
  earlier to `POST /cases/generate`. **Not yet done for this route: the ruling
  is still not spoken.** It returns as JSON to a dialog, where every graph
  ruling is streamed and synthesized.
- **LLMOps (#7).** Cost and latency are metered per call (`app/telemetry.py`)
  and reported by `eval:courtroom`. Every eval run is now recorded to MLflow
  (`eval/tracking.py` — metrics, the settings and commit that produced them, and
  the printed report as an artifact; `pnpm run eval:ui` to compare). The store is
  local SQLite and gitignored, so a fresh clone has no history and the recorded
  baselines in `docs/evaluation.md` remain the thing to quote. **Docker is done
  and verified end to end on 2026-08-20**: `docker compose up --build` brings up
  Postgres, a one-shot init container, the AI service, Express and nginx, and the
  running stack was checked by response code (`/api/healthz` 200, `/api/cases`
  200, `/api/auth/me` 401), by corpus state (53/53 embedded) and by a live
  retrieval that put QSO 71 first for a hearsay query and kept the
  `[UNVERIFIED TEXT ...]` marker on Const. Art. 199. Host ports are `DOCKER_*_PORT`
  and offset from the dev-server ports on purpose — `API_PORT` is the Vite dev
  proxy target, so reusing it collided with `pnpm run dev:api`. The cross-encoder
  reranker moved to an opt-in `crossencoder` extra, which is what keeps the AI
  image at 748 MB rather than ~3 GB. Still missing: per-call tracing, CI, and
  surfacing cost per *session* in the app rather than only in the harness.
- **Security & contract fixes (#8).** User scoping is **done**: `users` (scrypt
  password hashing), a stateless signed session cookie, and rate limiting keyed
  on both email and IP (`lib/auth.ts`, `lib/rate-limit.ts`). `requireUser` is
  mounted on the whole `/sessions` and `/dashboard` routers — verified by
  response code: `/cases` stays 200 as a shared library while `/auth/me`,
  `/dashboard`, `POST /sessions` and `POST /sessions/:id/voice-turns` all return
  401 unauthenticated. **`AUTH_SECRET` (32+ chars) has no default and
  `getSecret()` throws without it**, so a tree with a stale `.env` boots, serves
  `/cases`, and then fails only at sign-in. Model claims were reconciled against
  code on 2026-08-17 and the README table is accurate; `MODEL_AUDIO` (the
  conversational audio path, default `gpt-4o-audio-preview`) is the one env var
  the README does not list. The prompt-injection guard is **deliberately not
  built**:
  `pnpm run eval:redteam` puts 36 attacks through the courtroom and the verdict
  scorer and 0 land, because opposing counsel objects to injected instructions
  as irrelevant. Build the guard when an attack lands, and add the attack first.
- **Corpus verification — done, 53 of 53** (2026-08-20). Art. 199 was diffed
  clean against `data/statutes/administrator9d8e2ecc414c6d3371ac41114b61a2c4.pdf`, which turned out to be a post-Twenty-seventh-Amendment
  (2025) print, not merely post-26th. The same run caught **Art. 10** as stale —
  the corpus had "Chief Justice of Pakistan" where the 2025 print reads "Chief
  Justice of Supreme Court of Pakistan" — so it was corrected and re-embedded.
  Two consequences to carry forward: the Constitution's `sourceUrl` is still the
  2012 NA print and wants replacing with the canonical URL of the 2025 one, and
  **no provision is unverified any more, so the ⚠ badge and the
  `[UNVERIFIED TEXT ...]` marker currently never fire.** The machinery is intact
  and must stay (§2) — it simply has nothing to flag. `docs/practice-script.md`
  built a demo beat on Art. 199 reading ⚠ and has been rewritten accordingly.

---

## 7. Environment

pnpm workspace · Node 24 · Python 3.12+ · PostgreSQL with `pg_trgm` · a **single
`.env` at the repo root** read by all three services (`app/config.py` resolves it
two levels up). Dev servers: `pnpm run dev:ai` (:8000), `pnpm run dev:api`
(:5000), `pnpm run dev` (:5173). Windows host — prefer the documented pnpm
scripts over hand-rolled shell.

**`AUTH_SECRET` (32+ characters) has no default and is the one variable whose
absence is not obvious.** The server boots, `/cases` serves, and sign-in returns
500 — because `getSecret()` throws lazily, only when a token is signed. A tree
whose `.env` predates the scoping work looks healthy until someone registers.
Generate one with
`node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`.

---

## 8. Completion gate

A task is done when all of these hold:

- The requested change works, and existing behaviour still works.
- No invariant in §1 was broken, and no honesty marker in §2 was weakened.
- The relevant gate in §4 was actually run, and the output was reported —
  including regressions.
- If retrieval, prompts, agents, or scoring changed: `pnpm run eval` was re-run
  and the delta stated.
- The affected doc (`docs/agents.md`, `docs/retrieval.md`, `docs/evaluation.md`,
  or the README **Status** section) reflects the new behaviour.
- What could not be verified here — anything touching audio — is called out
  explicitly rather than assumed working.

Success is measured by whether this project can be demonstrated, defended with
numbers, and trusted with the law. Not by how much was built.
