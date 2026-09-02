"""Retrieval evaluation: does the corpus return the provision that governs a question?

Runs a golden set of legal questions through the hybrid retriever and scores the
ranking with the standard IR metrics — hit@k and Mean Reciprocal Rank. It can run
with reranking on and off to quantify what the reranker actually buys, and it
splits results by whether a query rewards semantic or lexical retrieval, so a
regression in one half of the hybrid does not hide behind the other.

    python -m eval.retrieval_eval                 # reranked (default)
    python -m eval.retrieval_eval --no-rerank     # fusion only
    python -m eval.retrieval_eval --compare       # both, side by side
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.rag.index import get_index
from app.rag.retrieval import search_statutes

GOLD_PATH = Path(__file__).parent / "datasets" / "retrieval_gold.json"
RETRIEVE_K = 10
HIT_LEVELS = (1, 3, 5)


@dataclass(slots=True)
class CaseResult:
    id: str
    mode: str
    expected: list[str]
    retrieved: list[str]
    first_rank: int | None  # 1-based rank of the first expected citation

    def hit_at(self, k: int) -> bool:
        return self.first_rank is not None and self.first_rank <= k

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.first_rank if self.first_rank else 0.0


def _first_rank(retrieved: list[str], expected: list[str]) -> int | None:
    wanted = set(expected)
    for rank, citation in enumerate(retrieved, start=1):
        if citation in wanted:
            return rank
    return None


async def _run_case(case: dict, rerank: bool) -> CaseResult:
    results = await search_statutes(case["query"], top_k=RETRIEVE_K, rerank=rerank)
    retrieved = [item.section.citation for item in results]
    return CaseResult(
        id=case["id"],
        mode=case.get("mode", "unspecified"),
        expected=case["expected"],
        retrieved=retrieved,
        first_rank=_first_rank(retrieved, case["expected"]),
    )


async def evaluate_retrieval(rerank: bool) -> list[CaseResult]:
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["cases"]
    # Sequential rather than gathered: reranking calls the model, and a burst of
    # concurrent calls buys nothing here and risks rate limits.
    return [await _run_case(case, rerank) for case in gold]


def summarise(results: list[CaseResult]) -> dict:
    n = len(results)
    if n == 0:
        return {}
    summary = {f"hit@{k}": sum(r.hit_at(k) for r in results) / n for k in HIT_LEVELS}
    summary["mrr"] = sum(r.reciprocal_rank for r in results) / n
    return summary


def _by_mode(results: list[CaseResult]) -> dict[str, list[CaseResult]]:
    modes: dict[str, list[CaseResult]] = {}
    for r in results:
        modes.setdefault(r.mode, []).append(r)
    return modes


def print_report(results: list[CaseResult], label: str) -> None:
    print(f"\n=== Retrieval eval · {label} · {len(results)} queries ===\n")
    print(f"  {'query':<22} {'mode':<9} {'rank':>5}  expected")
    for r in results:
        rank = str(r.first_rank) if r.first_rank else "MISS"
        flag = "" if r.first_rank and r.first_rank <= 3 else "  <-- "
        print(
            f"  {r.id:<22} {r.mode:<9} {rank:>5}  {', '.join(r.expected)}{flag}"
        )

    overall = summarise(results)
    print("\n  overall:  " + "  ".join(f"{k}={v:.2f}" for k, v in overall.items()))
    for mode, group in sorted(_by_mode(results).items()):
        s = summarise(group)
        print(
            f"  {mode:<9} " + "  ".join(f"{k}={v:.2f}" for k, v in s.items())
            + f"   (n={len(group)})"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval evaluation")
    parser.add_argument("--no-rerank", action="store_true", help="fusion only")
    parser.add_argument(
        "--compare", action="store_true", help="run with and without reranking"
    )
    args = parser.parse_args()

    await db.init_pool()
    index = await get_index()
    print(f"corpus: {index.size} provisions, {index.embedded_count} embedded")

    try:
        if args.compare:
            fusion = await evaluate_retrieval(rerank=False)
            reranked = await evaluate_retrieval(rerank=True)
            print_report(fusion, "fusion only (RRF)")
            print_report(reranked, "reranked (LLM)")
            _print_delta(summarise(fusion), summarise(reranked))
        else:
            rerank = not args.no_rerank
            results = await evaluate_retrieval(rerank=rerank)
            print_report(results, "reranked (LLM)" if rerank else "fusion only (RRF)")
    finally:
        await db.close_pool()


def _print_delta(fusion: dict, reranked: dict) -> None:
    print("\n=== Reranker contribution (reranked − fusion) ===\n")
    for key in reranked:
        delta = reranked[key] - fusion[key]
        sign = "+" if delta >= 0 else ""
        print(f"  {key:<7} {fusion[key]:.2f} -> {reranked[key]:.2f}  ({sign}{delta:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
