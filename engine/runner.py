import asyncio
import logging
import time
from typing import List, Dict
from dataclasses import dataclass, field
from tqdm.asyncio import tqdm

# USD per 1K tokens — {model: {input_rate, output_rate}}
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o":            {"input": 0.0025,   "output": 0.0100},
    "gpt-4o-mini":       {"input": 0.000150, "output": 0.000600},
    "claude-sonnet-4-6": {"input": 0.003,    "output": 0.015},
    "claude-haiku-4-5":  {"input": 0.00025,  "output": 0.00125},
}
# When only total tokens are known, assume 40% input / 60% output
_DEFAULT_INPUT_RATIO = 0.4


def _calc_cost(model: str, tokens: int) -> float:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    input_tok  = tokens * _DEFAULT_INPUT_RATIO
    output_tok = tokens * (1 - _DEFAULT_INPUT_RATIO)
    return (input_tok * pricing["input"] + output_tok * pricing["output"]) / 1000


@dataclass
class _Record:
    model: str
    tokens: int
    cost: float


@dataclass
class CostTracker:
    _records: List[_Record] = field(default_factory=list)

    def add(self, model: str, tokens: int) -> None:
        self._records.append(_Record(model, tokens, _calc_cost(model, tokens)))

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens for r in self._records)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost for r in self._records)

    def print_report(self) -> None:
        agg: Dict[str, Dict] = {}
        for r in self._records:
            if r.model not in agg:
                agg[r.model] = {"tokens": 0, "cost": 0.0}
            agg[r.model]["tokens"] += r.tokens
            agg[r.model]["cost"]   += r.cost

        W = 48
        sep = "=" * W
        print(f"\n+{sep}+")
        print(f"|{'  COST & TOKEN REPORT':^{W}}|")
        print(f"+{sep}+")
        print(f"|  {'Model':<22} {'Tokens':>8}  {'Cost (USD)':>10}  |")
        print(f"+{sep}+")
        for model, data in agg.items():
            print(f"|  {model:<22} {data['tokens']:>8,}  ${data['cost']:>9.5f}  |")
        print(f"+{sep}+")
        print(f"|  {'TOTAL':<22} {self.total_tokens:>8,}  ${self.total_cost_usd:>9.5f}  |")
        print(f"+{sep}+\n")

    def summary(self) -> Dict:
        return {
            "total_tokens":   self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "calls":          len(self._records),
        }


class BenchmarkRunner:
    def __init__(self, agent, evaluator, judge, max_concurrency: int = 10):
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge
        self.max_concurrency = max_concurrency
        self.cost_tracker = CostTracker()

    async def run_single_test(self, test_case: Dict) -> Dict:
        question = test_case["question"]
        start_time = time.perf_counter()

        response = await self.agent.query(test_case["question"])
        latency  = time.perf_counter() - start_time

        ragas_scores = await self.evaluator.score(test_case, response)

        judge_result = await self.judge.evaluate_multi_judge(
            test_case["question"],
            response["answer"],
            test_case["expected_answer"],
        )

        metadata    = response.get("metadata", {})
        tokens_used = metadata.get("tokens_used", 0)
        model       = metadata.get("model", "gpt-4o-mini")

        return {
            "test_case":      test_case["question"],
            "agent_response": response["answer"],
            "latency":        latency,
            "ragas":          ragas_scores,
            "judge":          judge_result,
            "tokens_used":    tokens_used,
            "model":          model,
            "status":         "fail" if judge_result["final_score"] < 3 else "pass",
        }

    async def run_all(self, dataset: List[Dict]) -> List[Dict]:
        """
        Chạy tất cả test cases song song với asyncio.Semaphore kiểm soát concurrency,
        tqdm.asyncio hiển thị progress bar + ETA, CostTracker tổng hợp chi phí.
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)
        wall_start = time.perf_counter()

        async def _run(case: Dict) -> Dict:
            async with semaphore:
                result = await self.run_single_test(case)
                self.cost_tracker.add(result["model"], result["tokens_used"])
                return result

        tasks = [_run(case) for case in dataset]
        results = await tqdm.gather(
            *tasks,
            desc=f"Benchmarking (concurrency={self.max_concurrency})",
            unit="case",
        )

        elapsed = time.perf_counter() - wall_start
        print(f"\n  Total time: {elapsed:.2f}s  |  Cases: {len(results)}")
        self.cost_tracker.print_report()

        return list(results)
