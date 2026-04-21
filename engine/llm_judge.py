"""
Multi-Judge Consensus (Người 4).

This module combines Judge A (``engine/llm_judge_a.py``) and Judge B
(``engine/llm_judge_b.py``) into a single Multi-Judge pipeline with:

- Parallel calls to both judges (``asyncio.gather``).
- Consensus rule:
    * If ``abs(score_A - score_B) <= DISAGREEMENT_THRESHOLD`` -> arithmetic mean.
    * If ``abs(score_A - score_B) > DISAGREEMENT_THRESHOLD`` -> tie-breaker:
        - A third judge is invoked if provided, else a weighted mean biased
          toward the lower (more conservative) judge is used.
- Per-case ``agreement_rate`` (1.0 - normalized diff on 1-5 scale).
- Cumulative ``Cohen's Kappa`` across the dataset on the accuracy dimension.
- Structured output: ``final_score``, ``agreement_rate``, ``cohen_kappa``,
  ``individual_scores``, ``consensus_method``, ``judge_a``, ``judge_b``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence

from engine.llm_judge_a import LLMJudge as LLMJudgeA
from engine.llm_judge_b import LLMJudge as LLMJudgeB


DISAGREEMENT_THRESHOLD = 1.0


def cohen_kappa(ratings_a: Sequence[Any], ratings_b: Sequence[Any]) -> Optional[float]:
    """
    Compute Cohen's Kappa for two raters on categorical labels.

    Returns ``None`` when there are fewer than 2 samples (kappa undefined).
    Returns ``1.0`` when all ratings match and ``p_e == 1`` (perfect agreement
    on a degenerate single-category case).
    """
    if len(ratings_a) != len(ratings_b):
        raise ValueError("ratings_a and ratings_b must have the same length")

    n = len(ratings_a)
    if n < 2:
        return None

    categories = sorted(set(ratings_a) | set(ratings_b))
    agree = sum(1 for a, b in zip(ratings_a, ratings_b) if a == b)
    p_o = agree / n

    p_e = 0.0
    for c in categories:
        pa = sum(1 for x in ratings_a if x == c) / n
        pb = sum(1 for x in ratings_b if x == c) / n
        p_e += pa * pb

    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0

    return (p_o - p_e) / (1 - p_e)


class LLMJudge:
    """
    Multi-Judge orchestrator. Kept the name ``LLMJudge`` so that
    ``engine/runner.py`` can use it as a drop-in replacement.
    """

    def __init__(
        self,
        judge_a: Optional[LLMJudgeA] = None,
        judge_b: Optional[LLMJudgeB] = None,
        tie_breaker: Optional[Any] = None,
        disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
    ):
        self.judge_a = judge_a if judge_a is not None else LLMJudgeA()
        self.judge_b = judge_b if judge_b is not None else LLMJudgeB()
        self.tie_breaker = tie_breaker
        self.disagreement_threshold = disagreement_threshold

        self._accuracy_history_a: List[int] = []
        self._accuracy_history_b: List[int] = []
        self._tone_history_a: List[int] = []
        self._tone_history_b: List[int] = []

    async def evaluate_multi_judge(
        self, question: str, answer: str, ground_truth: str
    ) -> Dict[str, Any]:
        result_a, result_b = await asyncio.gather(
            self.judge_a.evaluate_multi_judge(question, answer, ground_truth),
            self.judge_b.evaluate_multi_judge(question, answer, ground_truth),
        )

        score_a = float(result_a["final_score"])
        score_b = float(result_b["final_score"])
        diff = abs(score_a - score_b)

        tie_breaker_score: Optional[float] = None
        if diff <= self.disagreement_threshold:
            final_score = (score_a + score_b) / 2
            consensus_method = "average"
        else:
            if self.tie_breaker is not None:
                tb_raw = await self.tie_breaker.evaluate_multi_judge(
                    question, answer, ground_truth
                )
                tie_breaker_score = float(tb_raw["final_score"])
                final_score = (score_a + score_b + tie_breaker_score) / 3
                consensus_method = "tie_breaker_third_judge"
            else:
                lower, higher = sorted([score_a, score_b])
                final_score = 0.7 * lower + 0.3 * higher
                consensus_method = "weighted_conservative"

        case_agreement = round(1.0 - (diff / 4.0), 3)

        acc_a = int(result_a["criteria"]["accuracy"]["score"])
        acc_b = int(result_b["criteria"]["accuracy"]["score"])
        tone_a = int(result_a["criteria"]["tone"]["score"])
        tone_b = int(result_b["criteria"]["tone"]["score"])
        self._accuracy_history_a.append(acc_a)
        self._accuracy_history_b.append(acc_b)
        self._tone_history_a.append(tone_a)
        self._tone_history_b.append(tone_b)

        kappa_accuracy = cohen_kappa(
            self._accuracy_history_a, self._accuracy_history_b
        )
        kappa_tone = cohen_kappa(self._tone_history_a, self._tone_history_b)

        return {
            "final_score": round(final_score, 2),
            "agreement_rate": case_agreement,
            "cohen_kappa": {
                "accuracy": kappa_accuracy,
                "tone": kappa_tone,
            },
            "individual_scores": {
                result_a["model"]: score_a,
                result_b["model"]: score_b,
            },
            "consensus_method": consensus_method,
            "tie_breaker_score": tie_breaker_score,
            "judge_a": result_a,
            "judge_b": result_b,
            "reasoning": (
                f"A({result_a['model']})={score_a} | "
                f"B({result_b['model']})={score_b} | "
                f"method={consensus_method}"
            ),
        }

    def aggregate_stats(self) -> Dict[str, Any]:
        """
        Returns dataset-level agreement stats across all previous calls.

        Useful after running the whole benchmark to populate
        ``reports/summary.json`` with a stable Cohen's Kappa number.
        """
        n = len(self._accuracy_history_a)
        if n == 0:
            return {
                "num_samples": 0,
                "avg_agreement_rate": None,
                "cohen_kappa": {"accuracy": None, "tone": None},
            }

        diffs = [
            abs(a - b)
            for a, b in zip(self._accuracy_history_a, self._accuracy_history_b)
        ]
        avg_agreement = sum(1.0 - (d / 4.0) for d in diffs) / n

        return {
            "num_samples": n,
            "avg_agreement_rate": round(avg_agreement, 3),
            "cohen_kappa": {
                "accuracy": cohen_kappa(
                    self._accuracy_history_a, self._accuracy_history_b
                ),
                "tone": cohen_kappa(
                    self._tone_history_a, self._tone_history_b
                ),
            },
        }

    async def check_position_bias(
        self,
        question: str,
        response_a: str,
        response_b: str,
        ground_truth: str,
    ) -> Dict[str, Any]:
        """
        Delegates to Judge A's pairwise bias checker (it already implements the
        swap-order test). Kept here to preserve the public interface.
        """
        return await self.judge_a.check_position_bias(
            question, response_a, response_b, ground_truth
        )
