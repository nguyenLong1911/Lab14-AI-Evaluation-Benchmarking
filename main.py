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
    def __init__(self, retrieval: RetrievalEvaluator | None = None):
        self.retrieval = retrieval or RetrievalEvaluator()

    async def score(self, case: dict, response: dict) -> dict:
        expected_ids = case.get("ground_truth_context_ids", [])
        retrieved_ids = response.get("retrieved_ids", [])

        hit_rate = self.retrieval.calculate_hit_rate(expected_ids, retrieved_ids)
        mrr = self.retrieval.calculate_mrr(expected_ids, retrieved_ids)
        precision = self.retrieval.calculate_precision_at_k(expected_ids, retrieved_ids)
        recall = self.retrieval.calculate_recall_at_k(expected_ids, retrieved_ids)
        ndcg = self.retrieval.calculate_ndcg_at_k(expected_ids, retrieved_ids)
        f1 = self.retrieval.calculate_f1_at_k(expected_ids, retrieved_ids)

        return {
            "faithfulness": None,
            "relevancy": None,
            "retrieval": {
                "hit_rate": hit_rate,
                "mrr": mrr,
                "precision_at_k": precision,
                "recall_at_k": recall,
                "ndcg_at_k": ndcg,
                "f1_at_k": f1,
            }
        }


def _compute_summary(results: list, version: str, judge_stats: dict,
                     retrieval_detail: dict | None = None,
                     total_cost_usd: float = 0.0) -> dict:
    """Tổng hợp metrics từ danh sách kết quả từng test case."""
    total = len(results)
    if total == 0:
        return {}

    avg_score      = sum(r["judge"]["final_score"]           for r in results) / total
    hit_rate       = sum(r["ragas"]["retrieval"]["hit_rate"]  for r in results) / total
    avg_mrr        = sum(r["ragas"]["retrieval"]["mrr"]       for r in results) / total
    avg_precision  = sum(r["ragas"]["retrieval"]["precision_at_k"] for r in results) / total
    avg_recall     = sum(r["ragas"]["retrieval"]["recall_at_k"]    for r in results) / total
    avg_ndcg       = sum(r["ragas"]["retrieval"]["ndcg_at_k"]      for r in results) / total
    avg_f1         = sum(r["ragas"]["retrieval"]["f1_at_k"]        for r in results) / total
    agreement_rate = sum(r["judge"]["agreement_rate"]         for r in results) / total
    avg_latency    = sum(r["latency"]                         for r in results) / total
    pass_count     = sum(1 for r in results if r["status"] == "pass")

    # Final Answer Accuracy: điểm accuracy (1-5) trung bình từ 2 judge, chuẩn hóa về 0-1
    def _accuracy_score(r):
        a = r["judge"].get("judge_a", {}).get("criteria", {}).get("accuracy", {}).get("score", 0)
        b = r["judge"].get("judge_b", {}).get("criteria", {}).get("accuracy", {}).get("score", 0)
        scores = [s for s in [a, b] if s]
        return (sum(scores) / len(scores) / 5.0) if scores else r["judge"]["final_score"] / 5.0
    final_answer_accuracy = sum(_accuracy_score(r) for r in results) / total

    # Hallucination Rate: % cases bị judge đánh dấu safety=fail
    def _safety_fail(r):
        a = r["judge"].get("judge_a", {}).get("criteria", {}).get("safety", {}).get("verdict", "pass")
        b = r["judge"].get("judge_b", {}).get("criteria", {}).get("safety", {}).get("verdict", "pass")
        return 1 if (a == "fail" or b == "fail") else 0
    hallucination_rate = sum(_safety_fail(r) for r in results) / total

    rd = retrieval_detail or {}
    summary = {
        "metadata": {
            "version": version,
            "total": total,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pass_count": pass_count,
            "fail_count": total - pass_count,
            "pass_rate": round(pass_count / total, 4),
        },
        "metrics": {
            # Answer quality
            "avg_score":              round(avg_score, 4),
            "final_answer_accuracy":  round(final_answer_accuracy, 4),
            "hallucination_rate":     round(hallucination_rate, 4),
            "agreement_rate":         round(agreement_rate, 4),
            "cohen_kappa":            judge_stats.get("cohen_kappa"),
            # Retrieval — per-case averages
            "hit_rate":         round(hit_rate, 4),
            "avg_mrr":          round(avg_mrr, 4),
            "avg_precision_at_k": round(avg_precision, 4),
            "avg_recall_at_k":  round(avg_recall, 4),
            "avg_ndcg_at_k":    round(avg_ndcg, 4),
            "avg_f1_at_k":      round(avg_f1, 4),
            # Performance
            "avg_latency_sec":  round(avg_latency, 4),
            "total_tokens":     sum(r.get("tokens_used", 0) for r in results),
            "total_cost_usd":   round(total_cost_usd, 6),
        },
    }

    # Gắn metrics nâng cao từ evaluate_batch() nếu có
    if rd:
        summary["retrieval_detail"] = {
            "map":                  round(rd.get("map", 0.0), 4),
            "coverage":             round(rd.get("coverage", 0.0), 4),
            "miss_count":           rd.get("miss_count", 0),
            "mean_first_hit_rank":  rd.get("mean_first_hit_rank"),
            "hit_rate_at_k":        rd.get("hit_rate_at_k", {}),
            "recall_at_k":          rd.get("recall_at_k", {}),
            "precision_at_k":       rd.get("precision_at_k", {}),
            "ndcg_at_k":            rd.get("ndcg_at_k", {}),
            "f1_at_k":              rd.get("f1_at_k", {}),
            "avg_latency_ms":       round(rd.get("avg_latency_ms", 0.0), 2),
            "p50_latency_ms":       round(rd.get("p50_latency_ms", 0.0), 2),
            "p95_latency_ms":       round(rd.get("p95_latency_ms", 0.0), 2),
            "num_unanswerable":     rd.get("num_unanswerable", 0),
        }

    return summary


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


async def run_benchmark(agent_version: str, top_k: int = 3) -> tuple[list | None, dict | None]:
    print(f"\n🚀 Khởi động Benchmark cho {agent_version} (top_k={top_k})...")

    if not os.path.exists("data/golden_set.jsonl"):
        print("❌ Thiếu data/golden_set.jsonl. Hãy chạy 'python data/synthetic_gen.py' trước.")
        return None, None

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print("❌ File data/golden_set.jsonl rỗng. Hãy tạo ít nhất 1 test case.")
        return None, None

    agent = MainAgent(version=agent_version, top_k=top_k)
    evaluator = ExpertEvaluator()
    judge = LLMJudge()

    # Chạy benchmark (judge + per-case retrieval) song song với evaluate_batch (Weaviate)
    runner = BenchmarkRunner(MainAgent(), evaluator, judge)
    results, retrieval_detail = await asyncio.gather(
        runner.run_all(dataset),
        retrieval_evaluator.evaluate_batch(dataset),
    )

    judge_stats = judge.aggregate_stats()
    cost_summary = runner.cost_tracker.summary()
    summary = _compute_summary(results, version=agent_version,
                               judge_stats=judge_stats,
                               retrieval_detail=retrieval_detail,
                               total_cost_usd=cost_summary["total_cost_usd"])

    # Đóng HTTP client để tránh ResourceWarning về unclosed sockets
    await judge.judge_a.client.close()
    await judge.judge_b.client.close()

    return results, summary


async def main():
    v1_results, v1_summary = await run_benchmark("Agent_V1_Base", top_k=3)
    v2_results, v2_summary = await run_benchmark("Agent_V2_Optimized", top_k=5)

    if not v1_summary or not v2_summary:
        print("❌ Không thể chạy Benchmark. Kiểm tra lại data/golden_set.jsonl.")
        return

    gate = _evaluate_release_gate(v1_summary, v2_summary)

    m1, m2 = v1_summary["metrics"], v2_summary["metrics"]
    rd = v2_summary.get("retrieval_detail", {})

    print("\n📊 --- KẾT QUẢ SO SÁNH (REGRESSION) ---")
    print(f"  {'Metric':<26} {'V1':>8}  {'V2':>8}  {'Delta':>8}")
    print(f"  {'-'*54}")
    print(f"  {'Avg Score (1-5)':<26} {m1['avg_score']:>8.4f}  {m2['avg_score']:>8.4f}  {gate['delta_score']:>+8.4f}")
    print(f"  {'Hit Rate':<26} {m1['hit_rate']:>8.2%}  {m2['hit_rate']:>8.2%}  {gate['delta_hit_rate']:>+8.4f}")
    print(f"  {'Avg MRR':<26} {m1['avg_mrr']:>8.4f}  {m2['avg_mrr']:>8.4f}")
    print(f"  {'Precision@k':<26} {m1['avg_precision_at_k']:>8.4f}  {m2['avg_precision_at_k']:>8.4f}")
    print(f"  {'Recall@k':<26} {m1['avg_recall_at_k']:>8.4f}  {m2['avg_recall_at_k']:>8.4f}")
    print(f"  {'NDCG@k':<26} {m1['avg_ndcg_at_k']:>8.4f}  {m2['avg_ndcg_at_k']:>8.4f}")
    print(f"  {'F1@k':<26} {m1['avg_f1_at_k']:>8.4f}  {m2['avg_f1_at_k']:>8.4f}")
    print(f"  {'Agreement Rate':<26} {m1['agreement_rate']:>8.2%}  {m2['agreement_rate']:>8.2%}")
    print(f"  {'Avg Latency (s)':<26} {m1['avg_latency_sec']:>8.4f}  {m2['avg_latency_sec']:>8.4f}")
    if rd:
        print(f"\n  --- Retrieval Detail (Weaviate) ---")
        print(f"  {'MAP':<26} {rd.get('map', 0):>8.4f}")
        print(f"  {'Coverage':<26} {rd.get('coverage', 0):>8.2%}")
        print(f"  {'Miss Count':<26} {rd.get('miss_count', 0):>8}")
        print(f"  {'Mean First Hit Rank':<26} {str(rd.get('mean_first_hit_rank', 'N/A')):>8}")
        print(f"  {'p50 Latency (ms)':<26} {rd.get('p50_latency_ms', 0):>8.1f}")
        print(f"  {'p95 Latency (ms)':<26} {rd.get('p95_latency_ms', 0):>8.1f}")
    print(f"\n  Cost Change: {gate['cost_increase_pct']:+.1f}%  (giới hạn: +{GATE_MAX_COST_INCREASE:.0%})")
    print(f"  Checks:      {gate['checks']}")
    print(f"  Lý do:       {gate['reason']}")

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
