"""Courtroom evaluation: does opposing counsel object correctly, and rule right?

The judge eval measures the *grader*. This measures the *courtroom* — the two
decisions the multi-agent graph makes that a student actually experiences:

* **Does counsel object when it should, and stay silent when it should not?**
  Both halves matter. An advocate who never objects is scenery; one who objects
  to every question is noise. Reported as precision/recall over the objection
  decision, with the proper-question controls carrying the false-positive rate.
* **Does the bench rule correctly on what was raised?** A leading question in
  examination-in-chief should be sustained; the same question in
  cross-examination is permitted and should not draw an objection at all.

Ground scoring credits any ground in ``expectedGrounds`` rather than one right
answer, because more than one ground is genuinely defensible for the same
question — a foundationless character attack is both insulting and irrelevant.
Scoring a defensible choice as wrong would understate the agent and push future
work towards gaming a single label.

This drives ``run_turn`` — the same entry point the API calls — so the harness
cannot drift from the product.

    python -m eval.courtroom_eval
    python -m eval.courtroom_eval --limit 8 --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import db
from app.agents import TurnRequest, run_turn
from app.config import get_settings
from app.telemetry import track
from eval.tracking import tracked_run

GOLD_PATH = Path(__file__).parent / "datasets" / "objection_scenarios.json"
WRIT_PATH = Path(__file__).parent / "datasets" / "writ_scenarios.json"

# No session exists for a scenario, and none should: load_session_memory returns
# empty memory for an unknown id, which is exactly the blank slate we want.
SYNTHETIC_SESSION_ID = 0


@dataclass(slots=True)
class ScenarioResult:
    id: str
    group: str
    expect_objection: bool
    expected_grounds: list[str]
    expected_ruling: str | None

    objected: bool = False
    ground: str | None = None
    ruling: str | None = None
    witness_answered: bool = False
    seconds: float = 0.0
    error: str | None = None

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    models: dict[str, int] = field(default_factory=dict)

    @property
    def decision_correct(self) -> bool:
        return self.objected == self.expect_objection

    @property
    def ground_acceptable(self) -> bool | None:
        """None when no objection was raised, so it is not scored."""
        if not self.objected:
            return None
        return self.ground in self.expected_grounds

    @property
    def ruling_correct(self) -> bool | None:
        """None when nothing was ruled on, or no ruling was labelled."""
        if self.ruling is None or self.expected_ruling is None:
            return None
        return self.ruling == self.expected_ruling


def _group_of(scenario_id: str) -> str:
    return re.sub(r"_\d+$", "", scenario_id)


def _working_memory(case: dict, witness_name: str | None) -> list[dict]:
    """The witness taking the stand, so agents see the context the app gives them."""
    witness = next(
        (w for w in case["witnesses"] if w["name"] == witness_name), None
    )
    if witness is None:
        return []
    return [
        {
            "speaker": "witness",
            "witnessName": witness["name"],
            "transcript": (
                f"{witness['name']} takes the stand. \"{witness['statement']}\""
            ),
        }
    ]


async def _run_scenario(case: dict, scenario: dict) -> ScenarioResult:
    result = ScenarioResult(
        id=scenario["id"],
        group=_group_of(scenario["id"]),
        expect_objection=scenario["expectObjection"],
        expected_grounds=scenario.get("expectedGrounds", []),
        expected_ruling=scenario.get("expectedRuling"),
    )

    request = TurnRequest.model_validate(
        {
            "sessionId": SYNTHETIC_SESSION_ID,
            "phase": scenario["phase"],
            "studentSide": case["studentSide"],
            "activeWitness": scenario["activeWitness"],
            "case": case,
            "utterance": scenario["utterance"],
            "workingMemory": _working_memory(case, scenario["activeWitness"]),
        }
    )

    started = time.perf_counter()
    with track() as ledger:
        try:
            turn = await run_turn(request)
        except Exception as err:  # a failed scenario is data, not a crash
            result.error = f"{type(err).__name__}: {err}"
            result.seconds = time.perf_counter() - started
            return result
    result.seconds = time.perf_counter() - started
    result.calls = ledger.calls
    result.prompt_tokens = ledger.prompt_tokens
    result.completion_tokens = ledger.completion_tokens
    result.cost = ledger.cost
    result.models = ledger.by_model

    # The agents swallow model failures on purpose — a turn that cannot reach
    # the API stays silent rather than crashing the courtroom. That is right for
    # the product and poison for a harness: an outage reads as "counsel had no
    # objection" and the run reports a confident, wrong specificity. One real
    # run scored 0/5 on leading questions this way. No calls, no score.
    if ledger.calls == 0:
        result.error = "no model calls recorded — API failure, not a decision"

    objection = turn.get("objection")
    result.objected = objection is not None
    result.ground = objection.get("groundId") if objection else None

    for event in turn.get("events", []):
        if event.get("kind") == "ruling":
            result.ruling = event.get("ruling")
        if event.get("kind") == "testimony":
            result.witness_answered = True

    return result


async def evaluate_courtroom(
    limit: int | None = None, concurrency: int = 1
) -> list[ScenarioResult]:
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    case = gold["case"]
    scenarios = gold["scenarios"][:limit] if limit else gold["scenarios"]

    if concurrency <= 1:
        # Sequential by default so the per-scenario timings mean something.
        return [await _run_scenario(case, s) for s in scenarios]

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(scenario: dict) -> ScenarioResult:
        async with semaphore:
            return await _run_scenario(case, scenario)

    return list(await asyncio.gather(*(bounded(s) for s in scenarios)))


# ---------------------------------------------------------------------------
# Proceeding routing: a writ heard on the record
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProceedingResult:
    """One turn in a proceeding that engages no objection ground.

    Scored structurally rather than judged. Everything above measures a
    decision the model made and could defensibly have made differently; this
    measures the graph. A writ has no witness box and no applicable ground, so
    "counsel did not object" is not an opinion — it is an invariant, and a
    violation is a routing bug rather than a bad call.
    """

    id: str
    phase: str
    expected_speaker: str

    speaker: str | None = None
    objected: bool = False
    witness_answered: bool = False
    seconds: float = 0.0
    calls: int = 0
    cost: float = 0.0
    error: str | None = None

    @property
    def speaker_correct(self) -> bool:
        return self.speaker == self.expected_speaker

    @property
    def clean(self) -> bool:
        """No objection screened, and nobody seated in a box that does not exist."""
        return not self.objected and not self.witness_answered


async def _run_proceeding_scenario(case: dict, scenario: dict) -> ProceedingResult:
    result = ProceedingResult(
        id=scenario["id"],
        phase=scenario["phase"],
        expected_speaker=scenario["expectedSpeaker"],
    )

    request = TurnRequest.model_validate(
        {
            "sessionId": SYNTHETIC_SESSION_ID,
            "phase": scenario["phase"],
            "studentSide": case["studentSide"],
            # Passed through exactly as given, including the stale witness the
            # fixture carries. Sanitising it here would test the harness.
            "activeWitness": scenario["activeWitness"],
            "case": case,
            "utterance": scenario["utterance"],
            "workingMemory": [],
        }
    )

    started = time.perf_counter()
    with track() as ledger:
        try:
            turn = await run_turn(request)
        except Exception as err:  # a failed scenario is data, not a crash
            result.error = f"{type(err).__name__}: {err}"
            result.seconds = time.perf_counter() - started
            return result
    result.seconds = time.perf_counter() - started
    result.calls = ledger.calls
    result.cost = ledger.cost

    # Same reasoning as the objection suite: the agents swallow model failures,
    # so an outage would read here as a perfectly quiet courtroom. It is not.
    if ledger.calls == 0:
        result.error = "no model calls recorded — API failure, not a decision"

    result.objected = turn.get("objection") is not None
    result.speaker = turn.get("primarySpeaker")
    for event in turn.get("events", []):
        if event.get("kind") == "testimony":
            result.witness_answered = True

    return result


async def evaluate_proceeding(
    limit: int | None = None, concurrency: int = 1
) -> list[ProceedingResult]:
    gold = json.loads(WRIT_PATH.read_text(encoding="utf-8"))
    case = gold["case"]
    scenarios = gold["scenarios"][:limit] if limit else gold["scenarios"]

    if concurrency <= 1:
        return [await _run_proceeding_scenario(case, s) for s in scenarios]

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(scenario: dict) -> ProceedingResult:
        async with semaphore:
            return await _run_proceeding_scenario(case, scenario)

    return list(await asyncio.gather(*(bounded(s) for s in scenarios)))


def print_proceeding_report(results: list[ProceedingResult]) -> None:
    scored = [r for r in results if r.error is None]

    print()
    print(f"=== Writ routing · {len(results)} scenarios ===")
    print()
    print(f"  {'scenario':<26} {'speaker':<20} {'objected':>8} {'witness':>8} {'s':>5}")
    for r in results:
        if r.error:
            print(f"  {r.id:<26} ERROR  {r.error[:48]}")
            continue
        speaker = r.speaker or "-"
        if not r.speaker_correct:
            speaker += " (!)"
        print(
            f"  {r.id:<26} {speaker:<20} "
            f"{('YES' if r.objected else 'no'):>8} "
            f"{('YES' if r.witness_answered else 'no'):>8} {r.seconds:>5.1f}"
        )

    if not scored:
        print("  no scenarios completed")
        return

    objections = sum(1 for r in scored if r.objected)
    testimony = sum(1 for r in scored if r.witness_answered)
    speakers = sum(1 for r in scored if r.speaker_correct)

    print()
    print("  invariants (any non-zero is a routing bug, not a model opinion)")
    print(f"    objections raised where no ground applies:   {objections}")
    print(f"    testimony given where there is no stand:     {testimony}")
    print(
        f"    responding agent correct: {speakers}/{len(scored)} "
        f"({speakers / len(scored) * 100:.0f}%)"
    )
    wrong = [r for r in scored if not r.speaker_correct]
    if wrong:
        detail = ", ".join(
            f"{r.id}: expected {r.expected_speaker}, got {r.speaker}" for r in wrong
        )
        print(f"    mismatches: {detail}")

    total_cost = sum(r.cost for r in scored)
    print(
        f"  cost: ${total_cost:.4f} over {len(scored)} turns "
        f"= ${total_cost / len(scored):.4f}/turn, "
        f"{sum(r.calls for r in scored)} calls"
    )


def summarise_proceeding(results: list[ProceedingResult]) -> dict[str, float]:
    scored = [r for r in results if r.error is None]
    if not scored:
        return {
            "writ_speaker": 0.0,
            "writ_objection_leaks": 0.0,
            "writ_testimony_leaks": 0.0,
        }
    return {
        "writ_speaker": sum(1 for r in scored if r.speaker_correct) / len(scored),
        "writ_objection_leaks": float(sum(1 for r in scored if r.objected)),
        "writ_testimony_leaks": float(sum(1 for r in scored if r.witness_answered)),
    }


def _counts(results: list[ScenarioResult]) -> tuple[int, int, int, int]:
    tp = sum(1 for r in results if r.expect_objection and r.objected)
    fp = sum(1 for r in results if not r.expect_objection and r.objected)
    fn = sum(1 for r in results if r.expect_objection and not r.objected)
    tn = sum(1 for r in results if not r.expect_objection and not r.objected)
    return tp, fp, fn, tn


def print_report(results: list[ScenarioResult]) -> None:
    scored = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]

    print(f"\n=== Courtroom eval · {len(results)} scenarios ===\n")
    print(f"  {'scenario':<26} {'objected':>9} {'ground':<22} {'ruling':<10} {'s':>5}")
    for r in results:
        if r.error:
            print(f"  {r.id:<26} {'ERROR':>9}  {r.error[:44]}")
            continue
        mark = "ok " if r.decision_correct else "MISS"
        ground = r.ground or "-"
        if r.objected and r.ground_acceptable is False:
            ground += " (!)"
        ruling = r.ruling or "-"
        if r.ruling_correct is False:
            ruling += " (!)"
        print(
            f"  {r.id:<26} {('yes' if r.objected else 'no'):>6} {mark} "
            f"{ground:<22} {ruling:<10} {r.seconds:>5.1f}"
        )

    if not scored:
        print("\n  no scenarios completed")
        return

    tp, fp, fn, tn = _counts(scored)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    specificity = tn / (tn + fp) if (tn + fp) else 0.0

    print("\n  objection decision")
    print(f"    tp={tp}  fp={fp}  fn={fn}  tn={tn}")
    print(
        f"    precision={precision:.2f}  recall={recall:.2f}  f1={f1:.2f}  "
        f"specificity={specificity:.2f}"
    )
    if fp:
        noisy = ", ".join(r.id for r in scored if not r.expect_objection and r.objected)
        print(f"    over-objected on: {noisy}")
    if fn:
        missed = ", ".join(
            r.id for r in scored if r.expect_objection and not r.objected
        )
        print(f"    missed: {missed}")

    grounds = [r for r in scored if r.ground_acceptable is not None]
    if grounds:
        ok = sum(1 for r in grounds if r.ground_acceptable)
        print(
            f"\n  ground accuracy: {ok}/{len(grounds)} "
            f"({ok / len(grounds) * 100:.0f}%) of objections cited an acceptable ground"
        )

    rulings = [r for r in scored if r.ruling_correct is not None]
    if rulings:
        ok = sum(1 for r in rulings if r.ruling_correct)
        print(
            f"  ruling accuracy: {ok}/{len(rulings)} "
            f"({ok / len(rulings) * 100:.0f}%) of rulings matched the label"
        )

    # A sustained objection must stop the witness answering; that is the whole
    # point of the routing, so a violation is a graph bug, not a model opinion.
    leaks = [r for r in scored if r.ruling == "sustained" and r.witness_answered]
    print(f"  sustained-but-witness-answered: {len(leaks)}"
          + (f" ({', '.join(r.id for r in leaks)})" if leaks else ""))

    print("\n  by group")
    for group in sorted({r.group for r in scored}):
        rows = [r for r in scored if r.group == group]
        ok = sum(1 for r in rows if r.decision_correct)
        print(f"    {group:<26} {ok}/{len(rows)} decisions correct")

    times = sorted(r.seconds for r in scored)
    print(
        f"\n  latency: median {statistics.median(times):.1f}s  "
        f"p95 {times[max(0, int(len(times) * 0.95) - 1)]:.1f}s  "
        f"max {times[-1]:.1f}s"
    )

    settings = get_settings()
    total_cost = sum(r.cost for r in scored)
    models: dict[str, int] = {}
    for r in scored:
        for model, n in r.models.items():
            models[model] = models.get(model, 0) + n
    silent = [r for r in scored if not r.objected]
    raised = [r for r in scored if r.objected]

    print(
        f"\n  cost (cascade {'on' if settings.objection_cascade else 'off'}, "
        f"fast={settings.model_fast})"
    )
    print(
        f"    total ${total_cost:.4f} over {len(scored)} scenarios "
        f"= ${total_cost / len(scored):.4f}/turn"
    )
    print(
        f"    tokens: {sum(r.prompt_tokens for r in scored):,} in / "
        f"{sum(r.completion_tokens for r in scored):,} out, "
        f"{sum(r.calls for r in scored)} calls"
    )
    # Split by path, because the two are different products. A silent turn is
    # the common case and the one the voice session waits on before the witness
    # can speak; an objected turn is rarer and already carries the judge's ReAct
    # loop. A cascade that makes the first cheaper and the second slower is a
    # good trade only if the split says so.
    if silent:
        print(
            f"    silent turns  (n={len(silent)}): "
            f"${sum(r.cost for r in silent) / len(silent):.4f}/turn, "
            f"{statistics.median(r.seconds for r in silent):.1f}s median"
        )
    if raised:
        print(
            f"    objected turns(n={len(raised)}): "
            f"${sum(r.cost for r in raised) / len(raised):.4f}/turn, "
            f"{statistics.median(r.seconds for r in raised):.1f}s median"
        )
    print(f"    calls by model: {models}")

    if failed:
        print(f"  failed scenarios: {len(failed)}")

    print(
        "\n  NOTE: labels were written by an engineer from provisions whose text "
        "is still\n  unverified. Have a law student review them before quoting "
        "these numbers."
    )


def summarise(results: list[ScenarioResult]) -> dict[str, float]:
    """The headline metrics of one pass, for comparing repeat runs."""
    scored = [r for r in results if r.error is None]
    tp, fp, fn, _tn = _counts(scored)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    grounds = [r for r in scored if r.ground_acceptable is not None]
    rulings = [r for r in scored if r.ruling_correct is not None]
    return {
        "f1": (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        ),
        "precision": precision,
        "recall": recall,
        "ground": (
            sum(1 for r in grounds if r.ground_acceptable) / len(grounds)
            if grounds
            else 0.0
        ),
        "ruling": (
            sum(1 for r in rulings if r.ruling_correct) / len(rulings)
            if rulings
            else 0.0
        ),
    }


def print_stability(runs: list[dict[str, float]]) -> None:
    """Repeat-run spread.

    The objection decision is close to deterministic, but the bench's ruling is
    a separate model call and does move between identical runs. A single-run
    ruling figure is therefore not a number worth quoting — this is what makes
    it one.
    """
    print(f"\n=== Stability over {len(runs)} runs ===\n")
    print(f"  {'metric':<12} {'mean':>7} {'min':>7} {'max':>7} {'spread':>7}")
    for key in ("f1", "precision", "recall", "ground", "ruling"):
        values = [r[key] for r in runs]
        print(
            f"  {key:<12} {statistics.mean(values):>7.2f} {min(values):>7.2f} "
            f"{max(values):>7.2f} {max(values) - min(values):>7.2f}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Courtroom agent evaluation")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="repeat the suite N times; needed before quoting ruling accuracy",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="scenarios in flight; >1 is faster but makes the timings meaningless",
    )
    parser.add_argument(
        "--no-writ",
        action="store_true",
        help="skip the writ routing checks (trial scenarios only)",
    )
    args = parser.parse_args()

    if args.concurrency > 1:
        print("warning: concurrency > 1, latency figures are not comparable")

    await db.init_pool()
    try:
        with tracked_run(
            "courtroom",
            params={
                "runs": args.runs,
                "limit": args.limit,
                "concurrency": args.concurrency,
                "objection_cascade": get_settings().objection_cascade,
            },
        ) as recorder:
            summaries: list[dict[str, float]] = []
            costs: list[float] = []
            for run in range(args.runs):
                results = await evaluate_courtroom(args.limit, args.concurrency)
                if run == 0:
                    print_report(results)
                summaries.append(summarise(results))
                scored = [r for r in results if r.error is None]
                costs.append(sum(r.cost for r in scored) / len(scored) if scored else 0)
            if args.runs > 1:
                print_stability(summaries)

            # Run once regardless of --runs. These are invariants rather than
            # measurements that move between runs, so repeating them buys
            # nothing but spend.
            writ_metrics: dict[str, float] = {}
            if not args.no_writ:
                writ_results = await evaluate_proceeding(args.limit, args.concurrency)
                print_proceeding_report(writ_results)
                writ_metrics = summarise_proceeding(writ_results)

            # The mean across runs, not the last one: ruling accuracy moves
            # between identical runs and `CLAUDE.md` requires the mean be what
            # is quoted. Recording anything else would put a number in the
            # tracker that nobody is allowed to cite.
            recorded = {
                key: statistics.mean([s[key] for s in summaries])
                for key in (summaries[0] if summaries else {})
            }
            if costs:
                recorded["cost_per_turn_usd"] = statistics.mean(costs)
            recorded.update(writ_metrics)
            recorder.metrics("courtroom", recorded)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
