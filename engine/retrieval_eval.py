"""Retrieval evaluation module for the AI Evaluation Factory.

This module follows the contract defined in ``GUIDE_retrieval_eval.md``:

* The real vector database is **Weaviate Cloud**. Chunks were produced by
  ``data/chunking.py`` with explicit string IDs ``chunk_0`` … ``chunk_N`` and
  uploaded by ``data/weaviate_store.py index``. The collection is
  ``KnowledgeChunk`` and the queryable property carrying the ground-truth
  key is ``chunk_id``.
* Each test case in ``data/golden_set.jsonl`` stores ``ground_truth_context_ids``
  as a list of those same string IDs. The evaluator compares that list to the
  IDs returned by ``near_text``.
* ``RetrievalEvaluator.evaluate_batch`` is ``async`` and opens / closes the
  Weaviate client inside a ``try/finally`` block so the caller does not have
  to manage connection lifecycle.

On top of the guide's three primitives (Hit Rate, MRR, Precision@k) the
module additionally computes Recall@k, F1@k, NDCG@k, MAP, first-hit rank,
dataset coverage, and retrieval latency distributions — all of which were
asked for in earlier iterations and all of which are useful for failure
analysis and root-cause attribution (see the "Retrieval Quality ↔ Answer
Quality" section at the bottom of this docstring).

Flow
----
1. Load ``data/golden_set.jsonl``.
2. Open a Weaviate client.
3. For every question run ``near_text`` (top-K) to get the ordered list of
   ``chunk_id`` strings the retriever would put in the LLM's prompt.
4. Compare that list to ``ground_truth_context_ids`` using the metric
   primitives below.
5. Log every miss (question whose ground-truth chunk does not appear in the
   top-K) to stderr so the message can be piped into a failure-analysis
   report, and keep the same records in the returned summary under
   ``"misses"`` for programmatic downstream use.

Retrieval Quality ↔ Answer Quality
----------------------------------
In a RAG system the generator is upper-bounded by the context it receives.
Every retrieval metric here corresponds to a distinct failure mode of the
downstream answer:

* Low **Hit Rate / Recall@k** → the correct chunk is absent from the prompt,
  so the LLM must either refuse or hallucinate (the *Insufficient Context* /
  *Hallucination* failure class in ``data/knowledge_base.txt`` §4).
* Low **MRR / first-hit rank** → the correct chunk is present but buried
  among distractors; LLMs attend more to the first/last chunks ("lost in the
  middle"), so faithfulness drops even though the info was technically
  provided.
* Low **Precision@k / NDCG@k** → the prompt window is polluted with
  irrelevant chunks, wasting tokens (cost, latency) and pulling the
  generator off-source.
* Low **Coverage** → whole regions of the KB are never retrieved. That is
  an *ingestion / chunking* defect, not a generator defect, and is exactly
  the distinction the 5-Whys analysis is supposed to surface.

This is why the SOP in the README requires proving retrieval quality before
trusting any generation-side score.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery

# Load env at import time so Weaviate credentials are available for any
# downstream caller. The .env file lives at the repo root.
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger("retrieval_eval")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "KnowledgeChunk"
GOLDEN_SET_FILE = Path(__file__).parent.parent / "data" / "golden_set.jsonl"
DEFAULT_REPORT_FILE = Path(__file__).parent.parent / "reports" / "retrieval_eval.json"
DEFAULT_K_VALUES: Tuple[int, ...] = (1, 3, 5, 10)


# ---------------------------------------------------------------------------
# Weaviate helpers
# ---------------------------------------------------------------------------


def get_client() -> weaviate.WeaviateClient:
    """Open a Weaviate Cloud client using credentials from ``.env``."""

    url = os.environ.get("WEAVIATE_URL")
    api_key = os.environ.get("WEAVIATE_API_KEY")
    if not url or not api_key:
        raise RuntimeError(
            "WEAVIATE_URL / WEAVIATE_API_KEY must be set in .env before running "
            "retrieval evaluation. See GUIDE_retrieval_eval.md §2."
        )
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=Auth.api_key(api_key),
    )


def query_weaviate(
    client: weaviate.WeaviateClient,
    question: str,
    top_k: int = 3,
) -> List[str]:
    """Run ``near_text`` and return the ordered list of chunk_id strings.

    Returned IDs are guaranteed to be in the same string space as
    ``ground_truth_context_ids`` (``"chunk_0"`` .. ``"chunk_N"``), so the
    metric primitives below can compare them directly.
    """

    collection = client.collections.use(COLLECTION_NAME)
    response = collection.query.near_text(
        query=question,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True),
    )
    return [obj.properties["chunk_id"] for obj in response.objects]


# ---------------------------------------------------------------------------
# RetrievalEvaluator
# ---------------------------------------------------------------------------


class RetrievalEvaluator:
    """Compute Hit Rate@k, MRR, Precision@k and a richer metric suite.

    The evaluator is agnostic of the retrieval backend: it only cares about
    the ordered list of chunk IDs that ``query_weaviate`` returns per question.
    Swap ``query_weaviate`` for any function with the same contract and all
    metrics below keep working unchanged.
    """

    def __init__(
        self,
        top_k: int = 3,
        k_values: Tuple[int, ...] = DEFAULT_K_VALUES,
        concurrency: int = 5,
    ) -> None:
        self.top_k = top_k
        self.k_values = tuple(sorted(set(k_values)))
        self.concurrency = max(1, concurrency)
        self.misses: List[Dict] = []

    # ---------------------------------------------------------------------
    # Metric primitives
    #
    # These preserve the exact signatures from the guide (top-k defaults to
    # ``self.top_k``) and additionally accept an optional explicit ``top_k``
    # so the same functions can drive a multi-K sweep.
    # ---------------------------------------------------------------------

    def _k(self, top_k: Optional[int]) -> int:
        return self.top_k if top_k is None else top_k

    def calculate_hit_rate(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
        top_k: Optional[int] = None,
    ) -> float:
        """1.0 if any ``expected_id`` appears in the top-k retrieved, else 0.0."""

        k = self._k(top_k)
        if not expected_ids or k <= 0:
            return 0.0
        top = retrieved_ids[:k]
        return 1.0 if any(eid in top for eid in expected_ids) else 0.0

    def calculate_mrr(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
    ) -> float:
        """Reciprocal rank of the first relevant chunk (0.0 if none)."""

        if not expected_ids:
            return 0.0
        expected_set = set(expected_ids)
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_set:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_precision_at_k(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
        top_k: Optional[int] = None,
    ) -> float:
        """Precision@k = #relevant in top-k divided by k."""

        k = self._k(top_k)
        if k <= 0 or not retrieved_ids:
            return 0.0
        top = retrieved_ids[:k]
        expected_set = set(expected_ids)
        hits = sum(1 for doc_id in top if doc_id in expected_set)
        return hits / float(k)

    def calculate_recall_at_k(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
        top_k: Optional[int] = None,
    ) -> float:
        """Recall@k = fraction of all relevant chunks retrieved in top-k."""

        k = self._k(top_k)
        if not expected_ids or k <= 0:
            return 0.0
        top = set(retrieved_ids[:k])
        hits = sum(1 for eid in expected_ids if eid in top)
        return hits / float(len(expected_ids))

    def calculate_f1_at_k(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
        top_k: Optional[int] = None,
    ) -> float:
        """Harmonic mean of precision and recall at k."""

        p = self.calculate_precision_at_k(expected_ids, retrieved_ids, top_k)
        r = self.calculate_recall_at_k(expected_ids, retrieved_ids, top_k)
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    def calculate_ndcg_at_k(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
        top_k: Optional[int] = None,
    ) -> float:
        """Normalised Discounted Cumulative Gain (binary relevance)."""

        k = self._k(top_k)
        if not expected_ids or k <= 0:
            return 0.0
        expected_set = set(expected_ids)
        dcg = 0.0
        for i, doc_id in enumerate(retrieved_ids[:k]):
            if doc_id in expected_set:
                dcg += 1.0 / math.log2(i + 2)
        ideal_hits = min(len(expected_ids), k)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
        return dcg / idcg if idcg > 0 else 0.0

    def calculate_average_precision(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
    ) -> float:
        """AP over the full ranking. Mean across queries gives MAP."""

        if not expected_ids:
            return 0.0
        expected_set = set(expected_ids)
        hits = 0
        cumulative_precision = 0.0
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_set:
                hits += 1
                cumulative_precision += hits / (i + 1)
        if hits == 0:
            return 0.0
        return cumulative_precision / float(len(expected_ids))

    def calculate_first_hit_rank(
        self,
        expected_ids: List[str],
        retrieved_ids: List[str],
    ) -> Optional[int]:
        """1-indexed rank of the first relevant chunk, or ``None`` if missed."""

        if not expected_ids:
            return None
        expected_set = set(expected_ids)
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_set:
                return i + 1
        return None

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _resolve_expected_ids(case: Dict) -> List[str]:
        """Read ground-truth chunk IDs straight from the golden set."""

        for key in ("ground_truth_context_ids", "expected_retrieval_ids", "expected_ids"):
            value = case.get(key)
            if value:
                return [str(v) for v in value]
        return []

    async def _retrieve(
        self,
        client: weaviate.WeaviateClient,
        question: str,
        top_k: int,
        semaphore: asyncio.Semaphore,
    ) -> Tuple[List[str], float]:
        async with semaphore:
            start = time.perf_counter()
            retrieved = await asyncio.to_thread(query_weaviate, client, question, top_k)
            latency_ms = (time.perf_counter() - start) * 1000.0
            return retrieved, latency_ms

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        k = (len(ordered) - 1) * pct
        lo = math.floor(k)
        hi = math.ceil(k)
        if lo == hi:
            return ordered[lo]
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)

    # ---------------------------------------------------------------------
    # Batch evaluation
    # ---------------------------------------------------------------------

    async def evaluate_batch(
        self,
        dataset: List[Dict],
        client: Optional[weaviate.WeaviateClient] = None,
    ) -> Dict:
        """Run the retrieval evaluation over the whole dataset.

        Parameters
        ----------
        dataset
            List of test cases loaded from ``data/golden_set.jsonl``. Each
            case must contain ``question`` and ``ground_truth_context_ids``.
        client
            Optional pre-opened Weaviate client. If omitted, this method
            opens one and closes it when finished (``try/finally``).
        """

        max_k = max(self.k_values) if self.k_values else self.top_k
        effective_top_k = max(self.top_k, max_k)

        if not dataset:
            logger.warning("evaluate_batch called with empty dataset")
            return self._empty_summary(effective_top_k)

        own_client = client is None
        if own_client:
            logger.info("Connecting to Weaviate Cloud collection %r…", COLLECTION_NAME)
            client = get_client()

        try:
            logger.info(
                "Starting retrieval evaluation | cases=%d | top_k=%d | sweep=%s | concurrency=%d",
                len(dataset),
                effective_top_k,
                list(self.k_values),
                self.concurrency,
            )

            semaphore = asyncio.Semaphore(self.concurrency)
            retrievals = await asyncio.gather(
                *[
                    self._retrieve(client, case.get("question", ""), effective_top_k, semaphore)
                    for case in dataset
                ]
            )

            return self._aggregate(dataset, retrievals, effective_top_k)
        finally:
            if own_client:
                client.close()

    # ---------------------------------------------------------------------
    # Aggregation
    # ---------------------------------------------------------------------

    def _aggregate(
        self,
        dataset: List[Dict],
        retrievals: List[Tuple[List[str], float]],
        effective_top_k: int,
    ) -> Dict:
        per_case: List[Dict] = []
        misses: List[Dict] = []
        unanswerable: List[int] = []
        retrieved_universe: set = set()
        relevant_universe: set = set()
        covered_relevant: set = set()

        sum_primary_hit = 0.0
        sum_primary_precision = 0.0
        sum_rr = 0.0
        sum_ap = 0.0
        sums_hit_at_k: Dict[int, float] = {k: 0.0 for k in self.k_values}
        sums_recall_at_k: Dict[int, float] = {k: 0.0 for k in self.k_values}
        sums_precision_at_k: Dict[int, float] = {k: 0.0 for k in self.k_values}
        sums_ndcg_at_k: Dict[int, float] = {k: 0.0 for k in self.k_values}
        sums_f1_at_k: Dict[int, float] = {k: 0.0 for k in self.k_values}
        first_hit_ranks: List[int] = []
        latencies_ms: List[float] = []
        scored_cases = 0

        for idx, (case, (retrieved_ids, latency_ms)) in enumerate(zip(dataset, retrievals)):
            expected_ids = self._resolve_expected_ids(case)
            retrieved_universe.update(retrieved_ids)
            latencies_ms.append(latency_ms)

            if not expected_ids:
                unanswerable.append(idx)
                per_case.append(
                    {
                        "index": idx,
                        "question": case.get("question", ""),
                        "expected_ids": [],
                        "retrieved_ids": retrieved_ids,
                        "unanswerable": True,
                        "latency_ms": latency_ms,
                    }
                )
                continue

            relevant_universe.update(expected_ids)
            covered_relevant.update(e for e in expected_ids if e in retrieved_ids)

            primary_hit = self.calculate_hit_rate(expected_ids, retrieved_ids)
            primary_prec = self.calculate_precision_at_k(expected_ids, retrieved_ids)
            rr = self.calculate_mrr(expected_ids, retrieved_ids)
            ap = self.calculate_average_precision(expected_ids, retrieved_ids)
            first_rank = self.calculate_first_hit_rank(expected_ids, retrieved_ids)
            if first_rank is not None:
                first_hit_ranks.append(first_rank)

            sum_primary_hit += primary_hit
            sum_primary_precision += primary_prec
            sum_rr += rr
            sum_ap += ap
            scored_cases += 1

            hits_k: Dict[int, float] = {}
            recall_k: Dict[int, float] = {}
            precision_k: Dict[int, float] = {}
            ndcg_k: Dict[int, float] = {}
            f1_k: Dict[int, float] = {}
            for k in self.k_values:
                h = self.calculate_hit_rate(expected_ids, retrieved_ids, top_k=k)
                r = self.calculate_recall_at_k(expected_ids, retrieved_ids, top_k=k)
                p = self.calculate_precision_at_k(expected_ids, retrieved_ids, top_k=k)
                n = self.calculate_ndcg_at_k(expected_ids, retrieved_ids, top_k=k)
                f = self.calculate_f1_at_k(expected_ids, retrieved_ids, top_k=k)
                hits_k[k] = h
                recall_k[k] = r
                precision_k[k] = p
                ndcg_k[k] = n
                f1_k[k] = f
                sums_hit_at_k[k] += h
                sums_recall_at_k[k] += r
                sums_precision_at_k[k] += p
                sums_ndcg_at_k[k] += n
                sums_f1_at_k[k] += f

            record = {
                "index": idx,
                "question": case.get("question", ""),
                "expected_ids": expected_ids,
                "retrieved_ids": retrieved_ids,
                "hit_rate": primary_hit,
                "precision_at_k": primary_prec,
                "reciprocal_rank": rr,
                "average_precision": ap,
                "first_hit_rank": first_rank,
                "latency_ms": latency_ms,
                "hit_rate_at_k": hits_k,
                "recall_at_k": recall_k,
                "precision_at_k_sweep": precision_k,
                "ndcg_at_k": ndcg_k,
                "f1_at_k": f1_k,
            }
            per_case.append(record)

            if primary_hit == 0.0:
                logger.warning(
                    "MISS #%d | q=%r | expected=%s | top%d retrieved=%s",
                    idx,
                    (case.get("question", "") or "")[:100],
                    expected_ids,
                    effective_top_k,
                    retrieved_ids,
                )
                misses.append(record)

        self.misses = misses
        n = max(scored_cases, 1)

        summary = {
            # ---- Guide-compliant headline fields -------------------------
            "total": len(dataset),
            "avg_hit_rate": sum_primary_hit / n,
            "avg_mrr": sum_rr / n,
            f"avg_precision@{self.top_k}": sum_primary_precision / n,
            "miss_count": len(misses),

            # ---- Extended bookkeeping ------------------------------------
            "num_cases": len(dataset),
            "num_scored": scored_cases,
            "num_unanswerable": len(unanswerable),
            "top_k": effective_top_k,
            "k_values": list(self.k_values),
            "hit_top_k": self.top_k,
            "precision_top_k": self.top_k,

            "avg_precision_at_k": sum_primary_precision / n,
            "mrr": sum_rr / n,
            "map": sum_ap / n,
            "mean_first_hit_rank": (
                sum(first_hit_ranks) / len(first_hit_ranks) if first_hit_ranks else None
            ),
            "hit_rate_at_k": {k: sums_hit_at_k[k] / n for k in self.k_values},
            "recall_at_k": {k: sums_recall_at_k[k] / n for k in self.k_values},
            "precision_at_k": {k: sums_precision_at_k[k] / n for k in self.k_values},
            "ndcg_at_k": {k: sums_ndcg_at_k[k] / n for k in self.k_values},
            "f1_at_k": {k: sums_f1_at_k[k] / n for k in self.k_values},

            "coverage": (
                len(covered_relevant) / len(relevant_universe)
                if relevant_universe
                else 0.0
            ),
            "num_unique_chunks_retrieved": len(retrieved_universe),
            "num_unique_relevant_chunks": len(relevant_universe),

            "avg_latency_ms": sum(latencies_ms) / max(len(latencies_ms), 1),
            "p50_latency_ms": self._percentile(latencies_ms, 0.50),
            "p95_latency_ms": self._percentile(latencies_ms, 0.95),

            "misses": misses,
            "unanswerable_indices": unanswerable,
            "per_case": per_case,
        }

        logger.info(
            "Retrieval metrics | HR@%d=%.3f | MRR=%.3f | MAP=%.3f | P@%d=%.3f | "
            "NDCG@%d=%.3f | Coverage=%.3f | p95_latency=%.1fms | misses=%d/%d "
            "(unanswerable=%d)",
            self.top_k,
            summary["avg_hit_rate"],
            summary["mrr"],
            summary["map"],
            self.top_k,
            summary["avg_precision_at_k"],
            self.top_k,
            summary["ndcg_at_k"].get(self.top_k, 0.0),
            summary["coverage"],
            summary["p95_latency_ms"],
            len(misses),
            scored_cases,
            len(unanswerable),
        )
        return summary

    def _empty_summary(self, top_k: int) -> Dict:
        zero_k = {k: 0.0 for k in self.k_values}
        return {
            "total": 0,
            "avg_hit_rate": 0.0,
            "avg_mrr": 0.0,
            f"avg_precision@{self.top_k}": 0.0,
            "miss_count": 0,
            "num_cases": 0,
            "num_scored": 0,
            "num_unanswerable": 0,
            "top_k": top_k,
            "k_values": list(self.k_values),
            "hit_top_k": self.top_k,
            "precision_top_k": self.top_k,
            "avg_precision_at_k": 0.0,
            "mrr": 0.0,
            "map": 0.0,
            "mean_first_hit_rank": None,
            "hit_rate_at_k": dict(zero_k),
            "recall_at_k": dict(zero_k),
            "precision_at_k": dict(zero_k),
            "ndcg_at_k": dict(zero_k),
            "f1_at_k": dict(zero_k),
            "coverage": 0.0,
            "num_unique_chunks_retrieved": 0,
            "num_unique_relevant_chunks": 0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "misses": [],
            "unanswerable_indices": [],
            "per_case": [],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> List[Dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        inner = ", ".join(
            f"@{k}={v:.4f}" if isinstance(v, float) else f"@{k}={v}"
            for k, v in value.items()
        )
        return "{ " + inner + " }"
    return str(value)


async def _run_cli(
    golden_path: Path,
    report_path: Path,
    top_k: int,
    concurrency: int,
) -> None:
    if not golden_path.exists():
        logger.error(
            "Golden set not found at %s. Run `python data/synthetic_gen.py` first.",
            golden_path,
        )
        return

    dataset = _load_jsonl(golden_path)
    logger.info("Loaded %d test cases from %s", len(dataset), golden_path)

    evaluator = RetrievalEvaluator(top_k=top_k, concurrency=concurrency)
    summary = await evaluator.evaluate_batch(dataset)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    logger.info("Saved detailed retrieval report to %s", report_path)

    # Headline block matching GUIDE_retrieval_eval.md §5 expected output,
    # plus the extended metrics for the full picture.
    print("\n── Retrieval Eval Results ──")
    headline_keys = [
        "total",
        "avg_hit_rate",
        "avg_mrr",
        f"avg_precision@{top_k}",
        "miss_count",
    ]
    for key in headline_keys:
        print(f"  {key}: {_format_value(summary[key])}")

    print("\n── Extended metrics ──")
    extended_keys = [
        "map",
        "mean_first_hit_rank",
        "hit_rate_at_k",
        "recall_at_k",
        "precision_at_k",
        "ndcg_at_k",
        "f1_at_k",
        "coverage",
        "num_unique_chunks_retrieved",
        "num_unique_relevant_chunks",
        "avg_latency_ms",
        "p50_latency_ms",
        "p95_latency_ms",
        "num_unanswerable",
    ]
    for key in extended_keys:
        if key in summary:
            print(f"  {key}: {_format_value(summary[key])}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval quality against Weaviate Cloud "
                    "(Hit Rate, MRR, Precision@k, Recall@k, NDCG@k, MAP, Coverage)",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN_SET_FILE,
        help="Path to golden_set.jsonl (default: data/golden_set.jsonl)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Where to write the detailed JSON report (default: reports/retrieval_eval.json)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Top-K used as the primary evaluation depth (default: 3)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="How many Weaviate queries to run in parallel (default: 5)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        _run_cli(
            golden_path=args.golden,
            report_path=args.report,
            top_k=args.top_k,
            concurrency=args.concurrency,
        )
    )
