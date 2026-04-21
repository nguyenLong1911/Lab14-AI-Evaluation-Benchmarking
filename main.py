import asyncio
import json
import os
import time
from engine.runner import BenchmarkRunner
from engine.retrieval_eval import RetrievalEvaluator
from engine.llm_judge import LLMJudge
from agent.main_agent import MainAgent

# --- THRESHOLDS cho Release Gate ---
GATE_MIN_DELTA_SCORE = 0.0       # V2 phải tốt hơn V1
GATE_MIN_HIT_RATE = 0.8          # Retrieval phải đạt >= 80%
GATE_MAX_COST_INCREASE = 0.20    # Chi phí không được tăng > 20%


class ExpertEvaluator:
    """
    Wrapper kết nối RetrievalEvaluator (Người 2) với interface mà BenchmarkRunner cần.
    """
    def __init__(self):
        self.retrieval = RetrievalEvaluator()

    async def score(self, case: dict, response: dict) -> dict:
        expected_ids = case.get("ground_truth_context_ids", [])
        retrieved_ids = response.get("retrieved_ids", [])

        hit_rate = self.retrieval.calculate_hit_rate(expected_ids, retrieved_ids)
        mrr = self.retrieval.calculate_mrr(expected_ids, retrieved_ids)

        return {
            "faithfulness": None,
            "relevancy": None,
            "retrieval": {
                "hit_rate": hit_rate,
                "mrr": mrr
            }
        }


def _compute_summary(results: list, version: str, judge_stats: dict, total_cost_usd: float = 0.0) -> dict:
    """Tổng hợp metrics từ danh sách kết quả từng test case."""
    total = len(results)
    if total == 0:
        return {}

    avg_score = sum(r["judge"]["final_score"] for r in results) / total
    hit_rate = sum(r["ragas"]["retrieval"]["hit_rate"] for r in results) / total
    avg_mrr = sum(r["ragas"]["retrieval"]["mrr"] for r in results) / total
    agreement_rate = sum(r["judge"]["agreement_rate"] for r in results) / total
    avg_latency = sum(r["latency"] for r in results) / total
    pass_count = sum(1 for r in results if r["status"] == "pass")

    return {
        "metadata": {
            "version": version,
            "total": total,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pass_count": pass_count,
            "fail_count": total - pass_count,
            "pass_rate": round(pass_count / total, 4)
        },
        "metrics": {
            "avg_score": round(avg_score, 4),
            "hit_rate": round(hit_rate, 4),
            "avg_mrr": round(avg_mrr, 4),
            "agreement_rate": round(agreement_rate, 4),
            "cohen_kappa": judge_stats.get("cohen_kappa"),
            "avg_latency_sec": round(avg_latency, 4),
            "total_cost_usd": round(total_cost_usd, 6)
        }
    }


def _evaluate_release_gate(v1_summary: dict, v2_summary: dict) -> dict:
    """
    Release Gate: so sánh V1 vs V2, quyết định APPROVE hoặc ROLLBACK.

    Điều kiện APPROVE (cả 3 phải đúng):
      1. delta_score > 0         — V2 phải tốt hơn V1
      2. hit_rate >= 0.8         — Retrieval đạt ngưỡng tối thiểu
      3. cost_increase <= 20%    — Chi phí không tăng quá mức
    """
    v1_metrics = v1_summary["metrics"]
    v2_metrics = v2_summary["metrics"]

    delta_score = round(v2_metrics["avg_score"] - v1_metrics["avg_score"], 4)
    delta_hit_rate = round(v2_metrics["hit_rate"] - v1_metrics["hit_rate"], 4)

    v1_cost = v1_metrics.get("total_cost_usd", 0)
    v2_cost = v2_metrics.get("total_cost_usd", 0)
    cost_increase = (v2_cost - v1_cost) / v1_cost if v1_cost > 0 else 0.0

    checks = {
        "score_improved": delta_score > GATE_MIN_DELTA_SCORE,
        "hit_rate_ok": v2_metrics["hit_rate"] >= GATE_MIN_HIT_RATE,
        "cost_ok": cost_increase <= GATE_MAX_COST_INCREASE
    }

    reasons = []
    if not checks["score_improved"]:
        reasons.append(f"delta_score={delta_score:+.4f} <= 0 (V2 không cải thiện)")
    if not checks["hit_rate_ok"]:
        reasons.append(f"hit_rate={v2_metrics['hit_rate']:.2%} < {GATE_MIN_HIT_RATE:.0%}")
    if not checks["cost_ok"]:
        reasons.append(f"cost_increase={cost_increase:.1%} > {GATE_MAX_COST_INCREASE:.0%}")

    approved = all(checks.values())

    return {
        "decision": "APPROVE" if approved else "ROLLBACK",
        "approved": approved,
        "delta_score": delta_score,
        "delta_hit_rate": delta_hit_rate,
        "cost_increase_pct": round(cost_increase * 100, 2),
        "checks": checks,
        "reason": "; ".join(reasons) if reasons else "Tất cả điều kiện đạt — V2 tốt hơn V1"
    }


async def run_benchmark(agent_version: str) -> tuple[list | None, dict | None]:
    print(f"\n🚀 Khởi động Benchmark cho {agent_version}...")

    if not os.path.exists("data/golden_set.jsonl"):
        print("❌ Thiếu data/golden_set.jsonl. Hãy chạy 'python data/synthetic_gen.py' trước.")
        return None, None

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print("❌ File data/golden_set.jsonl rỗng. Hãy tạo ít nhất 1 test case.")
        return None, None

    agent = MainAgent()
    evaluator = ExpertEvaluator()
    judge = LLMJudge()

    runner = BenchmarkRunner(agent, evaluator, judge)
    results = await runner.run_all(dataset)

    judge_stats = judge.aggregate_stats()
    summary = _compute_summary(results, version=agent_version, judge_stats=judge_stats)
    return results, summary


async def main():
    v1_results, v1_summary = await run_benchmark("Agent_V1_Base")
    v2_results, v2_summary = await run_benchmark("Agent_V2_Optimized")

    if not v1_summary or not v2_summary:
        print("❌ Không thể chạy Benchmark. Kiểm tra lại data/golden_set.jsonl.")
        return

    gate = _evaluate_release_gate(v1_summary, v2_summary)

    print("\n📊 --- KẾT QUẢ SO SÁNH (REGRESSION) ---")
    print(f"  V1 Score:    {v1_summary['metrics']['avg_score']:.4f}")
    print(f"  V2 Score:    {v2_summary['metrics']['avg_score']:.4f}")
    print(f"  Delta Score: {gate['delta_score']:+.4f}")
    print(f"  Hit Rate:    {v2_summary['metrics']['hit_rate']:.2%}  (ngưỡng: {GATE_MIN_HIT_RATE:.0%})")
    print(f"  Cohen Kappa: {v2_summary['metrics']['cohen_kappa']}")
    print(f"  Cost Change: {gate['cost_increase_pct']:+.1f}%  (giới hạn: +{GATE_MAX_COST_INCREASE:.0%})")
    print(f"\n  Checks: {gate['checks']}")
    print(f"  Lý do:  {gate['reason']}")

    if gate["approved"]:
        print("\n✅ QUYẾT ĐỊNH: APPROVE — CHẤP NHẬN BẢN CẬP NHẬT")
    else:
        print("\n❌ QUYẾT ĐỊNH: ROLLBACK — TỪ CHỐI PHÁT HÀNH")

    v2_summary["regression"] = gate

    os.makedirs("reports", exist_ok=True)

    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    print("\n💾 Đã lưu reports/summary.json")

    benchmark_output = {
        "v1": {"summary": v1_summary, "results": v1_results},
        "v2": {"summary": v2_summary, "results": v2_results}
    }
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(benchmark_output, f, ensure_ascii=False, indent=2)
    print("💾 Đã lưu reports/benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
