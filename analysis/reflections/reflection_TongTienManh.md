# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- **Họ và tên:** Tống Tiến Mạnh
- **Mã sinh viên:** 2A202600494
- **Vai trò được phân công:**  DevOps/Analyst
- **File phụ trách chính:** `main.py`, `reports/summary.json`, `reports/benchmark_results.json`
- **Mục tiêu:** Xây dựng pipeline điều phối toàn bộ hệ thống benchmark, kết nối các module từ các thành viên khác, implement Release Gate tự động quyết định APPROVE/ROLLBACK khi phát hành phiên bản mới của AI Agent.

---

## 2. Phạm vi công việc được giao

1. Thay thế `ExpertEvaluator` và `MultiModelJudge` giả lập bằng class thật từ Người 2, 3, 4
2. Implement Release Gate logic trong `main()`:
   - APPROVE nếu: `delta_score > 0` VÀ `hit_rate >= 0.8` VÀ chi phí không tăng > 20%
   - ROLLBACK nếu bất kỳ điều kiện nào fail, kèm lý do cụ thể
3. Lưu `reports/summary.json` với trường `regression` chứa delta, decision, reason
4. Lưu `reports/benchmark_results.json` với toàn bộ kết quả chi tiết từng case

---

## 3. Công việc đã thực hiện

### 3.1. Kết nối các module thật
Xóa các class giả lập và import trực tiếp từ các module của thành viên khác:
```python
from engine.retrieval_eval import RetrievalEvaluator  # Người 2
from engine.llm_judge import LLMJudge                 # Người 3 & 4
from agent.main_agent import MainAgent                 # Người 8
```

Viết `ExpertEvaluator` làm wrapper kết nối `RetrievalEvaluator` với interface mà `BenchmarkRunner` cần, tính đồng thời 6 retrieval metrics: `hit_rate`, `mrr`, `precision@k`, `recall@k`, `ndcg@k`, `f1@k`.

### 3.2. Implement Release Gate với 3 điều kiện
```python
checks = {
    "score_improved": delta_score > 0,
    "hit_rate_ok":    hit_rate >= 0.8,
    "cost_ok":        cost_increase <= 0.20
}
```
Gate trả về `decision`, danh sách `checks`, và `reason` mô tả cụ thể điều kiện nào fail.

### 3.3. Tổng hợp metrics đầy đủ trong `_compute_summary()`
Tính trung bình toàn bộ 64 test cases và đóng gói vào 3 nhóm:

| Nhóm | Metrics |
|------|---------|
| Answer Quality | `avg_score`, `final_answer_accuracy`, `hallucination_rate`, `agreement_rate`, `cohen_kappa` |
| Retrieval | `hit_rate`, `avg_mrr`, `avg_precision_at_k`, `avg_recall_at_k`, `avg_ndcg_at_k`, `avg_f1_at_k` |
| Performance | `avg_latency_sec`, `total_tokens`, `total_cost_usd` |

Thêm `retrieval_detail` từ `evaluate_batch()` của Weaviate: `map`, `coverage`, `miss_count`, `mean_first_hit_rank`, `p50/p95 latency`.

### 3.4. Tính `final_answer_accuracy` và `hallucination_rate`
- **Final Answer Accuracy:** trích xuất `criteria.accuracy.score` (1–5) từ 2 judge, chuẩn hóa về 0–1
- **Hallucination Rate:** tính % cases bị judge đánh dấu `safety = fail`

### 3.5. Tích hợp Cost Tracking từ Người 5
Kết nối `runner.cost_tracker.summary()` để lấy `total_cost_usd` thực tế theo bảng giá token của từng model.

### 3.6. Chạy song song để tối ưu thời gian
```python
results, retrieval_detail = await asyncio.gather(
    runner.run_all(dataset),              # judge + per-case retrieval
    retrieval_evaluator.evaluate_batch(dataset),  # Weaviate full eval
)
```
Hai pipeline chạy đồng thời, không mất thêm thời gian chờ.

### 3.7. Sửa lỗi phát sinh
- **Bug `json.decoder.JSONDecodeError`** trong `llm_judge_a.py`: API trả về chuỗi whitespace-only, thứ tự `(content or "{}").strip()` sai khiến `json.loads("")` crash. Fix bằng hàm `_parse_json()` xử lý cả empty response và markdown wrapper.
- **`ResourceWarning` unclosed sockets:** Thêm `await judge.judge_a.client.aclose()` sau mỗi lần chạy để đóng HTTP connection đúng cách.
- **`ImportError` weaviate circular import:** Phát hiện gói `weaviate-client` cài thiếu thư mục `classes/`. Fix bằng `pip install --force-reinstall weaviate-client`.
- **Field name mismatch:** `golden_set.jsonl` dùng `ground_truth_context_ids` nhưng code đọc `ground_truth_doc_ids` → sửa lại đúng field.

---

## 4. Kết quả đạt được (Đối chiếu GRADING_RUBRIC)

| Tiêu chí | Yêu cầu | Kết quả |
|----------|---------|---------|
| Regression Testing | Chạy so sánh V1 vs V2, có Release Gate tự động | Đạt — Gate kiểm tra 3 điều kiện, in lý do cụ thể |
| Retrieval Evaluation | Có `hit_rate` trong summary | Đạt — có đủ `hit_rate`, `avg_mrr`, `ndcg`, `map`, `coverage` |
| Multi-Judge Metrics | Có `agreement_rate` | Đạt — thêm cả `cohen_kappa`, `final_answer_accuracy`, `hallucination_rate` |
| Performance | Báo cáo Cost & Token | Đạt — tích hợp `CostTracker`, lưu `total_cost_usd` và `total_tokens` |
| Output files | `summary.json` có trường `regression` | Đạt — đủ cả `metadata`, `metrics`, `retrieval_detail`, `regression` |

---

## 5. Khó khăn và cách xử lý

- **Khó khăn 1:** Phải chờ Người 2, 3, 4 hoàn thành module trước mới kết nối được.
  - **Xử lý:** Viết sẵn `ExpertEvaluator` và Release Gate với class giả lập để test logic độc lập. Khi nhận module thật thì swap vào không cần sửa lại logic.

- **Khó khăn 2:** `json.loads` crash khi API trả về response không phải JSON thuần — model `gemini-3-flash-preview` đôi khi wrap JSON trong markdown code block.
  - **Xử lý:** Viết hàm `_parse_json()` tách riêng, xử lý 3 trường hợp: empty, markdown wrapper, JSON lỗi. Đặt fallback để không crash toàn bộ pipeline.

- **Khó khăn 3:** `weaviate-client` bị cài không đầy đủ, thiếu thư mục `classes/`, gây `ImportError` ngay khi import.
  - **Xử lý:** Dùng `pip install --force-reinstall weaviate-client` để cài lại toàn bộ, xác nhận bằng import test trước khi chạy.

---

## 6. Bài học rút ra

- **Thiết kế interface trước khi chờ module:** Viết wrapper với interface chuẩn từ đầu giúp tích hợp nhanh khi nhận code từ thành viên khác, không bị block.
- **`asyncio.gather()` để chạy song song:** Việc chạy `runner.run_all()` và `evaluate_batch()` song song giúp tiết kiệm thời gian đáng kể khi dataset lớn.
- **Phòng thủ khi gọi API ngoài:** Luôn cần xử lý trường hợp API trả về ngoài spec (empty, markdown, timeout). Không nên `json.loads()` trực tiếp mà không có try/except hoặc validation.
- **Resource management trong async:** Các HTTP client tạo bởi `AsyncOpenAI` phải được đóng tường minh bằng `aclose()` để tránh rò rỉ socket.

---

## 7. Tự đánh giá đóng góp
- **Mức độ hoàn thành:** 100%
- **Đóng góp kỹ thuật chính:**
  - Implement `_evaluate_release_gate()` với logic 3 điều kiện và lý do cụ thể khi fail
  - Tổng hợp 14 metrics vào `summary.json` (nhiều hơn yêu cầu tối thiểu)
  - Chạy song song 2 pipeline bằng `asyncio.gather()` để tối ưu thời gian
  - Phát hiện và sửa 4 lỗi kỹ thuật: `JSONDecodeError`, `ResourceWarning`, `ImportError`, field name mismatch
  - Kết nối thành công toàn bộ module từ 5 thành viên (Người 2, 3, 4, 5, 8) vào 1 pipeline hoàn chỉnh
