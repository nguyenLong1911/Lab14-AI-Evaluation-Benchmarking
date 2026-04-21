import asyncio
import logging
import time
from typing import List, Dict

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    def __init__(self, agent, evaluator, judge):
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge

    async def run_single_test(self, test_case: Dict) -> Dict:
        question = test_case["question"]
        start_time = time.perf_counter()
        try:
            # 1. Gọi Agent
            response = await self.agent.query(question)
            latency = time.perf_counter() - start_time

            # 2. Chạy RAGAS metrics
            ragas_scores = await self.evaluator.score(test_case, response)

            # 3. Chạy Multi-Judge
            judge_result = await self.judge.evaluate_multi_judge(
                question,
                response["answer"],
                test_case["expected_answer"],
            )

            return {
                "test_case": question,
                "agent_response": response["answer"],
                "latency": latency,
                "ragas": ragas_scores,
                "judge": judge_result,
                "status": "fail" if judge_result["final_score"] < 3 else "pass",
            }
        except Exception as e:
            latency = time.perf_counter() - start_time
            logger.error("Test case error [%.80s]: %s", question, e)
            return {
                "test_case": question,
                "agent_response": "",
                "latency": latency,
                "ragas": {"retrieval": {"hit_rate": 0, "mrr": 0}},
                "judge": {"final_score": 1, "agreement_rate": 0, "criteria": {"accuracy": {"score": 1}, "tone": {"score": 1}}},
                "status": "error",
            }

    async def run_all(self, dataset: List[Dict], batch_size: int = 5) -> List[Dict]:
        """
        Chạy song song bằng asyncio.gather với giới hạn batch_size để không bị Rate Limit.
        """
        results = []
        for i in range(0, len(dataset), batch_size):
            batch = dataset[i:i + batch_size]
            tasks = [self.run_single_test(case) for case in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results
